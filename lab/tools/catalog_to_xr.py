#!/usr/bin/env python3
"""Convert APE catalog Resource entities into Crossplane XRs.

The scaffolder templates write Backstage catalog Resource entities under
  entities/dock-tech/systems/<ns>/resources/<env>/{record,zone}-*.yaml
These describe the desired DNS state but are NOT what Crossplane reconciles.
In real APE a controller converts them; in this lab that conversion is done
here (run by a GitHub Action on merge), emitting Crossplane XRs under
  entities/environments/<domain>/<subdomain>/<system>/<env>/resources/aws/<zoneName>/...
which the ArgoCD `entities` app already applies.

Canonical Resource contract this converter expects (denormalized so the
mapping is 1:1 with no cross-entity lookups):

  apiVersion: backstage.io/v1alpha1
  kind: Resource
  metadata:
    annotations:
      dock.tech/scaffolder-parameters: '<json>'   # carried through to the XR
      dock.tech/import-existing: "true"            # optional (claim only)
  spec:
    type: Record | Zone
    system: <system>            # e.g. infrastructure
    environment: <env>          # dev | hml | prd
    domain: <domain>            # e.g. cross
    subdomain: <subdomain>      # e.g. cloud
    aws: { account: <id>, accountName: <name> }
    zoneName: <fqdn-no-dot>     # e.g. arthurbryan.com
    # Record only:
    zoneId: <Z...>
    recordName: <zone-relative name, "" for apex>
    recordType: A|AAAA|CNAME|TXT|MX|SRV|NS|CAA|PTR|ALIAS
    ttl / values / aliasTarget / setIdentifier / weight / failover... etc.
    # Zone only:
    import: { existing: bool, zoneId: <Z...> }   # optional
    visibility / delegatedFromZoneId / ...        # passed through if present
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SOURCE_GLOB = "ape-platform-entities/dock-tech/systems/**/resources/**/*.yaml"
ENV_BASE = "ape-platform-entities/environments"
SYSTEM_CATALOG_GLOB = "ape-platform-entities/**/catalog-info.yaml"

# Annotation we stamp on every XR we generate so a future run can
# distinguish converter-produced XRs (safe to prune when orphaned) from
# manually-imported or hand-edited XRs (must be left alone).
GENERATED_MARKER_ANNOTATION = "dock.tech/generated-by"
GENERATED_MARKER_VALUE = "catalog-to-xr"


def build_system_index(root: Path) -> dict[str, tuple[str, str]]:
    """Map bare system name -> (domain, subdomain). APE-aligned Resources
    don't carry domain/subdomain in spec; we resolve them from the System
    entity's `dock.tech/{domain,subdomain}` annotations and stitch them
    onto the XR (which the XRD requires)."""
    index: dict[str, tuple[str, str]] = {}
    for src in root.glob(SYSTEM_CATALOG_GLOB):
        try:
            docs = list(yaml.safe_load_all(src.read_text()))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "System":
                continue
            name = (doc.get("metadata") or {}).get("name")
            ann = (doc.get("metadata") or {}).get("annotations") or {}
            d = ann.get("dock.tech/domain")
            s = ann.get("dock.tech/subdomain")
            if name and d and s:
                index[name] = (d, s)
    return index


def die(msg: str) -> None:
    print(f"catalog_to_xr: ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def aws_block(aws: dict | None) -> dict | None:
    """Normalize the aws block: account must be an int (the CRD requires a
    number; templates/catalog emit it as a string)."""
    if not aws:
        return None
    account = aws.get("account")
    if isinstance(account, str) and account.isdigit():
        account = int(account)
    return {"account": account, "accountName": aws.get("accountName")}


def warn(name: str, msg: str) -> None:
    print(f"catalog_to_xr: WARN [{name}]: {msg}", file=sys.stderr)


def require(spec: dict, keys: list[str], name: str) -> bool:
    missing = [k for k in keys if spec.get(k) in (None, "")]
    if missing:
        warn(name, f"missing required spec fields {missing}; skipping")
        return False
    return True


def normalize_system(value: str) -> str:
    """`spec.system` can be a bare name (`infrastructure`) or an EntityRef
    (`system:default/infrastructure`). The XR namespace and output path
    only want the bare name -- take the trailing path segment."""
    return value.rsplit("/", 1)[-1]


def record_xr_name(record_name: str, zone_name: str, rtype: str, set_id: str | None) -> str:
    if record_name:
        base = f"record-{record_name}.{zone_name}"
    else:
        base = f"record-apex-{rtype.lower()}.{zone_name}"
    if set_id:
        base = f"{base}-{set_id}".lower()
    return base


def build_record_xr(
    res: dict, system_index: dict[str, tuple[str, str]]
) -> tuple[str, dict] | None:
    spec = res.get("spec", {}) or {}
    ann = (res.get("metadata", {}) or {}).get("annotations", {}) or {}
    name = res.get("metadata", {}).get("name", "<unknown>")

    if not require(spec, ["system", "environment", "zoneName", "zoneId",
                          "recordType"], name):
        return None

    system = normalize_system(spec["system"])
    env = spec["environment"]
    # APE-aligned Resources don't carry domain/subdomain in spec; pick them
    # off the System entity. Fall back to spec.{domain,subdomain} for back-
    # compat with previously-imported Resources that still inline them.
    resolved = system_index.get(system)
    domain = spec.get("domain") or (resolved[0] if resolved else None)
    subdomain = spec.get("subdomain") or (resolved[1] if resolved else None)
    if not domain or not subdomain:
        warn(name, f"could not resolve domain/subdomain for system '{system}' "
                   f"(neither in spec nor catalog System annotations); skipping")
        return None
    zone_name = str(spec["zoneName"]).rstrip(".")
    record_name = (spec.get("recordName") or "").rstrip(".")
    # Defensive: if recordName came through as an FQDN, strip the zone suffix.
    if record_name.endswith("." + zone_name):
        record_name = record_name[: -(len(zone_name) + 1)]
    elif record_name == zone_name:
        record_name = ""
    rtype = spec["recordType"]
    set_id = spec.get("setIdentifier")

    xr_name = record_xr_name(record_name, zone_name, rtype, set_id)
    ns = f"system-{system}-{env}"

    xr_spec: dict = {
        "name": xr_name,
        "domain": domain,
        "subdomain": subdomain,
        "system": system,
        "environment": env,
        "zoneId": spec["zoneId"],
        "zoneName": zone_name,
        "recordName": record_name,
        "type": rtype,
    }
    aws = aws_block(spec.get("aws"))
    if aws:
        xr_spec["aws"] = aws

    if rtype == "ALIAS":
        at = spec.get("aliasTarget", {}) or {}
        xr_spec["aliasTarget"] = {k: v for k, v in {
            "serviceType": at.get("serviceType", "Custom"),
            "dnsName": at.get("dnsName"),
            "hostedZoneId": at.get("hostedZoneId"),
            "evaluateTargetHealth": at.get("evaluateTargetHealth", False),
            "region": at.get("region"),
        }.items() if v is not None}
    else:
        if spec.get("ttl") is not None:
            xr_spec["ttl"] = spec["ttl"]
        if spec.get("values"):
            xr_spec["values"] = list(spec["values"])

    # Routing policy passthrough (only when present).
    if set_id:
        xr_spec["setIdentifier"] = set_id
    if spec.get("weight") is not None:
        xr_spec["weight"] = spec["weight"]
    if spec.get("failoverType"):
        xr_spec["failoverRoutingPolicy"] = {"type": spec["failoverType"]}
    if spec.get("latencyRegion"):
        xr_spec["latencyRoutingPolicy"] = {"region": spec["latencyRegion"]}
    if spec.get("healthCheckId"):
        xr_spec["healthCheckId"] = spec["healthCheckId"]

    annotations = {GENERATED_MARKER_ANNOTATION: GENERATED_MARKER_VALUE}
    if ann.get("dock.tech/scaffolder-parameters"):
        annotations["dock.tech/scaffolder-parameters"] = ann["dock.tech/scaffolder-parameters"]
    # Pass through any argocd.argoproj.io/* annotations the template set
    # (e.g. sync-options: Force=true,Replace=true on type-changing edits, so
    # ArgoCD does delete-and-create instead of an in-place update that AWS
    # would reject for an immutable field).
    for k, v in ann.items():
        if k.startswith("argocd.argoproj.io/"):
            annotations[k] = v

    xr = {
        "apiVersion": "dock.tech/v1",
        "kind": "DNSRecord",
        "metadata": {"name": xr_name, "namespace": ns, "annotations": annotations},
        "spec": xr_spec,
    }

    out_path = (
        f"{ENV_BASE}/{domain}/{subdomain}/{system}/{env}/resources/aws/"
        f"{zone_name}/{xr_name}.yaml"
    )
    return out_path, xr


def build_zone_xr(
    res: dict, system_index: dict[str, tuple[str, str]]
) -> tuple[str, dict] | None:
    spec = res.get("spec", {}) or {}
    ann = (res.get("metadata", {}) or {}).get("annotations", {}) or {}
    name = res.get("metadata", {}).get("name", "<unknown>")

    if not require(spec, ["system", "environment", "zoneName"], name):
        return None

    system = normalize_system(spec["system"])
    env = spec["environment"]
    resolved = system_index.get(system)
    domain = spec.get("domain") or (resolved[0] if resolved else None)
    subdomain = spec.get("subdomain") or (resolved[1] if resolved else None)
    if not domain or not subdomain:
        warn(name, f"could not resolve domain/subdomain for system '{system}' "
                   f"(neither in spec nor catalog System annotations); skipping")
        return None
    zone_name = str(spec["zoneName"]).rstrip(".")
    xr_name = f"zone-{zone_name}"
    # Zones live in the System's home namespace regardless of which
    # AWS account hosts them -- spec.aws.account picks the target
    # account; the cluster XR/MR sit alongside the System catalog
    # entity. Records still use per-env (system-<system>-<env>).
    ns = f"system-{system}-prd"

    xr_spec: dict = {
        "name": xr_name,
        "domain": domain,
        "subdomain": subdomain,
        "system": system,
        "environment": env,
        "zoneName": zone_name,
    }
    aws = aws_block(spec.get("aws"))
    if aws:
        xr_spec["aws"] = aws
    for k in ("visibility", "delegatedFromZoneId", "delegatedFromAccountName",
              "comment", "vpcs"):
        if spec.get(k) is not None:
            xr_spec[k] = spec[k]
    if spec.get("import"):
        xr_spec["import"] = spec["import"]

    annotations = {GENERATED_MARKER_ANNOTATION: GENERATED_MARKER_VALUE}
    if ann.get("dock.tech/scaffolder-parameters"):
        annotations["dock.tech/scaffolder-parameters"] = ann["dock.tech/scaffolder-parameters"]

    xr = {
        "apiVersion": "dock.tech/v1",
        "kind": "DNSZone",
        "metadata": {"name": xr_name, "namespace": ns, "annotations": annotations},
        "spec": xr_spec,
    }

    # Zones live under the System's home env path (prd), same as the
    # namespace decision above. spec.environment + spec.aws.account
    # inside the XR carry the actual target.
    out_path = f"{ENV_BASE}/{domain}/{subdomain}/{system}/prd/resources/aws/{zone_name}/zone.yaml"
    return out_path, xr


RECORD_TYPES = {"dns-record", "Record"}
ZONE_TYPES = {"dns-zone", "Zone"}


def convert_one(
    res: dict, system_index: dict[str, tuple[str, str]]
) -> tuple[str, dict] | None:
    if res.get("kind") != "Resource":
        return None
    spec_type = (res.get("spec", {}) or {}).get("type")
    if spec_type in RECORD_TYPES:
        return build_record_xr(res, system_index)
    if spec_type in ZONE_TYPES:
        return build_zone_xr(res, system_index)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert APE catalog Resources to Crossplane XRs")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    ap.add_argument("--check", action="store_true",
                    help="Exit non-zero if any XR would change (CI drift check)")
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    sources = sorted(root.glob(SOURCE_GLOB))
    if not sources:
        print("catalog_to_xr: no catalog Resources found under "
              f"{SOURCE_GLOB}", file=sys.stderr)
        return 0
    system_index = build_system_index(root)

    changed = 0
    written = 0
    # Absolute paths the converter produced this run; everything in the
    # canonical XR tree that isn't here is an orphan and gets pruned.
    # This is what catches the "Resource still exists but its XR file
    # name changed" case -- e.g. enabling weighted routing renames the
    # XR from record-<fqdn>.yaml to record-<fqdn>-<setIdentifier>.yaml,
    # and without pruning the old XR survives as a stale MR.
    produced: set[Path] = set()
    # Per-(domain, subdomain, system) the converter actually visited.
    # We only prune in subtrees we touched, so a converter that fails
    # to process some system can't accidentally wipe its existing XRs.
    touched_systems: set[tuple[str, str, str]] = set()
    for src in sources:
        try:
            docs = list(yaml.safe_load_all(src.read_text()))
        except yaml.YAMLError as exc:
            warn(str(src), f"YAML parse error: {exc}")
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            result = convert_one(doc, system_index)
            if not result:
                continue
            rel_path, xr = result
            out = root / rel_path
            produced.add(out.resolve())
            xs = xr.get("spec", {})
            touched_systems.add((xs.get("domain"), xs.get("subdomain"), xs.get("system")))
            new_text = yaml.safe_dump(xr, sort_keys=False, default_flow_style=False)
            new_text = "---\n" + new_text
            old_text = out.read_text() if out.exists() else None
            if old_text == new_text:
                continue
            changed += 1
            if args.check:
                print(f"catalog_to_xr: DRIFT {rel_path}")
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(new_text)
            written += 1
            print(f"catalog_to_xr: wrote {rel_path}")

    # Prune orphan XR files. Strict criteria so we never touch a
    # manually-imported or hand-edited XR:
    #   (1) the file lives inside a system subtree we visited this run
    #   (2) the file isn't one we produced this run
    #   (3) the file carries our GENERATED_MARKER_ANNOTATION (proving a
    #       previous catalog_to_xr run wrote it)
    # Without (3) we'd risk removing legacy imports, which would cascade
    # into Crossplane deleting real Route53 records.
    pruned = 0
    for d, s, sysn in touched_systems:
        if not (d and s and sysn):
            continue
        system_root = root / ENV_BASE / d / s / sysn
        if not system_root.exists():
            continue
        for existing in system_root.glob("**/resources/aws/**/*.yaml"):
            n = existing.name
            if not (n.startswith("record-") or n == "zone.yaml"):
                continue
            if existing.resolve() in produced:
                continue
            try:
                docs = list(yaml.safe_load_all(existing.read_text()))
            except yaml.YAMLError:
                continue
            is_ours = any(
                isinstance(doc, dict)
                and ((doc.get("metadata") or {}).get("annotations") or {}).get(
                    GENERATED_MARKER_ANNOTATION) == GENERATED_MARKER_VALUE
                for doc in docs
            )
            if not is_ours:
                continue
            rel = existing.relative_to(root)
            if args.check:
                print(f"catalog_to_xr: PRUNE {rel}")
                changed += 1
            else:
                existing.unlink()
                pruned += 1
                print(f"catalog_to_xr: pruned {rel}")

    if args.check and changed:
        print(f"catalog_to_xr: {changed} XR(s) out of date", file=sys.stderr)
        return 1
    print(f"catalog_to_xr: done ({written} written, {changed} changed, {pruned} pruned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
