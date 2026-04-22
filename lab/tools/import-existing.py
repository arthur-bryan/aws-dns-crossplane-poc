#!/usr/bin/env python3
"""Batch-import existing Route53 zones + records under platform management.

Reads live state from AWS via the `aws` CLI, generates Zone/Record XR YAMLs
(with spec.import.existing=true and managementPolicies [Observe,Update] baked
in at composition level) plus matching Backstage Resource catalog entities,
and writes them under entities/. Idempotent: files that already exist are
left alone.

Usage:
  lab/tools/import-existing.py                 # dry-run: print what would change
  lab/tools/import-existing.py --write         # write the files
  lab/tools/import-existing.py --write --filter arthurbryan.com

After --write, review the generated files (`git status`, `git diff`), commit,
push, and open a PR. Argo sync + Crossplane observe then adopts everything.

Requires: aws CLI authenticated for Route53 read, python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Hierarchy defaults (match entities/catalog-info.yaml). Override via CLI.
# ---------------------------------------------------------------------------
DEFAULTS = {
    "domain": "cross",
    "subdomain": "cloud",
    "system": "infrastructure",
    "environment": "dev",
    "aws_account_name": "dev-account",
    "aws_region": "us-east-1",
}

# Routing policies we support. Records with others are skipped with a warning.
SUPPORTED_POLICIES: set[str] = {"Simple", "Weighted"}

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_DIR_TMPL = "entities/environments/{domain}/{subdomain}/{system}/{environment}/resources/aws"
CATALOG_ZONES_DIR = REPO_ROOT / "entities" / "catalog" / "zones"
CATALOG_RECORDS_DIR = REPO_ROOT / "entities" / "catalog" / "records"

REPO_URL = "https://github.com/arthur-bryan/aws-dns-crossplane-poc"
REPO_BRANCH = "feature/ape-platform-alignment"


# ---------------------------------------------------------------------------
# AWS helpers
# ---------------------------------------------------------------------------
def aws(*args: str) -> dict:
    """Run `aws ...` and return parsed JSON output."""
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR running `aws {' '.join(args)}`:\n{result.stderr}")
    return json.loads(result.stdout or "{}")


def get_caller_identity() -> dict:
    return aws("sts", "get-caller-identity")


def list_hosted_zones() -> list[dict]:
    data = aws("route53", "list-hosted-zones")
    return data.get("HostedZones", [])


def list_record_sets(zone_id: str) -> list[dict]:
    # paginate if needed (default list returns up to 100 records)
    records: list[dict] = []
    next_record = None
    next_type = None
    while True:
        args = ["route53", "list-resource-record-sets", "--hosted-zone-id", zone_id]
        if next_record:
            args += ["--start-record-name", next_record, "--start-record-type", next_type]
        page = aws(*args)
        records.extend(page.get("ResourceRecordSets", []))
        if not page.get("IsTruncated"):
            break
        next_record = page.get("NextRecordName")
        next_type = page.get("NextRecordType")
    return records


# ---------------------------------------------------------------------------
# YAML helpers — minimal hand-rolled writer so we don't need PyYAML.
# ---------------------------------------------------------------------------
def yaml_str(value: str) -> str:
    """YAML-quote a string when needed; preserve TXT quotes/backslashes."""
    if value == "":
        return '""'
    # Always use double-quoted YAML scalars to be safe with special chars.
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_list(items: list[str], indent: int) -> str:
    pad = " " * indent
    return "\n".join(f"{pad}- {yaml_str(v)}" for v in items)


# ---------------------------------------------------------------------------
# Zone import YAMLs
# ---------------------------------------------------------------------------
def zone_xr_yaml(ctx: dict, zone_name: str, zone_id: str) -> str:
    return dedent(f"""\
        ---
        # Managed by batch import ({ctx['aws_account_name']} / {zone_id}).
        # Removing this file unadopts the zone from the platform; the Route53
        # zone itself is NOT deleted (managementPolicies: [Observe, Update]).
        apiVersion: dock.tech/v1
        kind: Zone
        metadata:
          name: zone-{zone_name}
          namespace: system-{ctx['system']}-{ctx['environment']}
          annotations:
            dock.tech/managed-by: batch-import
        spec:
          name: zone-{zone_name}
          domain: {ctx['domain']}
          subdomain: {ctx['subdomain']}
          system: {ctx['system']}
          environment: {ctx['environment']}
          aws:
            account: {ctx['aws_account_id']}
            accountName: {ctx['aws_account_name']}
          zoneName: {zone_name}
          import:
            existing: true
            zoneId: {zone_id}
    """)


def zone_catalog_yaml(ctx: dict, zone_name: str, zone_id: str, xr_relpath: str) -> str:
    return dedent(f"""\
        ---
        apiVersion: backstage.io/v1alpha1
        kind: Resource
        metadata:
          name: zone-{zone_name}
          namespace: system-{ctx['system']}-{ctx['environment']}
          title: {zone_name}
          description: "Route53 Hosted Zone {zone_name} ({ctx['environment']}) — imported"
          annotations:
            dock.tech/xr-kind: Zone
            dock.tech/xr-name: zone-{zone_name}
            dock.tech/zone-name: {zone_name}
            dock.tech/zone-id: {zone_id}
            dock.tech/domain: {ctx['domain']}
            dock.tech/subdomain: {ctx['subdomain']}
            dock.tech/system: {ctx['system']}
            dock.tech/environment: {ctx['environment']}
            dock.tech/aws-account-id: "{ctx['aws_account_id']}"
            dock.tech/managed-by: batch-import
          tags:
            - aws
            - dns
            - route53
            - zone
            - imported
            - {ctx['environment']}
          links:
            - title: View in AWS Console
              url: https://console.aws.amazon.com/route53/v2/hostedzones#ListRecordSets/{zone_id}
              icon: cloud
            - title: View XR file on GitHub
              url: {REPO_URL}/blob/{REPO_BRANCH}/{xr_relpath}
              icon: github
            - title: Delete zone (opens GitHub delete UI)
              url: {REPO_URL}/delete/{REPO_BRANCH}/{xr_relpath}
              icon: delete
        spec:
          type: aws-dns-zone
          owner: group:application-platform-engineering
          system: {ctx['system']}
    """)


# ---------------------------------------------------------------------------
# Record import YAMLs
# ---------------------------------------------------------------------------
def record_xr_yaml(ctx: dict, rec: dict) -> str:
    """Generate a Record XR YAML that exactly matches the live AWS record so
    the first reconcile is a no-op."""
    # Lines that always apply
    head = dedent(f"""\
        ---
        # Managed by batch import.
        # Removing this file unadopts the record from the platform; the Route53
        # record itself is NOT deleted (managementPolicies: [Observe, Update]).
        apiVersion: dock.tech/v1
        kind: Record
        metadata:
          name: {rec['xr_name']}
          namespace: system-{ctx['system']}-{ctx['environment']}
          annotations:
            dock.tech/managed-by: batch-import
        spec:
          name: {rec['xr_name']}
          domain: {ctx['domain']}
          subdomain: {ctx['subdomain']}
          system: {ctx['system']}
          environment: {ctx['environment']}
          aws:
            account: {ctx['aws_account_id']}
            accountName: {ctx['aws_account_name']}
            region: {ctx['aws_region']}
          zoneId: {rec['zone_id']}
          zoneName: {rec['zone_name']}
          recordName: {rec['record_short']}
          type: {rec['type']}
        """)

    parts = [head.rstrip()]

    # ALIAS vs non-ALIAS body
    if rec["type"] == "ALIAS":
        parts.append("  aliasTarget:")
        parts.append(f"    serviceType: Custom")
        parts.append(f"    hostedZoneId: {rec['alias_zone_id']}")
        parts.append(f"    dnsName: {yaml_str(rec['alias_dns_name'])}")
        parts.append(f"    evaluateTargetHealth: {str(rec['alias_eval_target_health']).lower()}")
    else:
        parts.append(f"  ttl: {rec['ttl']}")
        parts.append("  values:")
        parts.append(yaml_list(rec["values"], indent=4))

    if rec.get("set_identifier"):
        parts.append(f"  setIdentifier: {yaml_str(rec['set_identifier'])}")
        parts.append(f"  weight: {rec['weight']}")

    parts.append("  import:")
    parts.append("    existing: true")
    parts.append("")  # trailing newline
    return "\n".join(parts)


def record_catalog_yaml(ctx: dict, rec: dict, xr_relpath: str) -> str:
    fqdn = f"{rec['record_short']}.{rec['zone_name']}"
    tags = ["aws", "dns", "route53", "record", rec["type"].lower(), "imported", ctx["environment"]]
    title = fqdn + (f" ({rec['set_identifier']})" if rec.get("set_identifier") else "")
    return dedent(f"""\
        ---
        apiVersion: backstage.io/v1alpha1
        kind: Resource
        metadata:
          name: {rec['xr_name']}
          namespace: system-{ctx['system']}-{ctx['environment']}
          title: {title}
          description: "DNS {rec['type']} record {fqdn} ({ctx['environment']}) — imported"
          annotations:
            dock.tech/xr-kind: Record
            dock.tech/xr-name: {rec['xr_name']}
            dock.tech/zone-name: {rec['zone_name']}
            dock.tech/zone-id: {rec['zone_id']}
            dock.tech/record-name: {rec['record_short']}
            dock.tech/record-type: {rec['type']}
            dock.tech/record-fqdn: {fqdn}
            dock.tech/domain: {ctx['domain']}
            dock.tech/subdomain: {ctx['subdomain']}
            dock.tech/system: {ctx['system']}
            dock.tech/environment: {ctx['environment']}
            dock.tech/managed-by: batch-import
          tags:
        """) + "\n".join(f"    - {t}" for t in tags) + dedent(f"""
          links:
            - title: Edit record
              url: /create/templates/default/aws-dns-record-edit?formData=%7B%22system%22%3A%22system%3Adefault%2F{ctx['system']}%22%2C%22environment%22%3A%22{ctx['environment']}%22%2C%22zoneName%22%3A%22{rec['zone_name']}%22%2C%22recordName%22%3A%22{rec['record_short']}%22%2C%22type%22%3A%22{rec['type']}%22%7D
              icon: edit
            - title: View in AWS Console
              url: https://console.aws.amazon.com/route53/v2/hostedzones#ListRecordSets/{rec['zone_id']}
              icon: cloud
            - title: View XR file on GitHub
              url: {REPO_URL}/blob/{REPO_BRANCH}/{xr_relpath}
              icon: github
            - title: Delete record (opens GitHub delete UI)
              url: {REPO_URL}/delete/{REPO_BRANCH}/{xr_relpath}
              icon: delete
        spec:
          type: aws-dns-record
          owner: group:application-platform-engineering
          system: {ctx['system']}
          dependsOn:
            - resource:default/zone-{rec['zone_name']}
        """)


# ---------------------------------------------------------------------------
# Record parsing — extract the shape our XR expects from AWS output.
# ---------------------------------------------------------------------------
def parse_record(rrset: dict, zone_name: str, zone_id: str) -> dict | None:
    """Return a normalized record dict or None to skip."""
    name = rrset["Name"].rstrip(".")  # AWS names have trailing dot
    rtype = rrset["Type"]

    # Skip apex NS/SOA — Route53 manages those automatically.
    if name == zone_name and rtype in ("NS", "SOA"):
        return None

    # Figure out the short name (recordName) relative to zone.
    if name == zone_name:
        record_short = "@"  # apex; we don't really support apex via our template yet
    elif name.endswith("." + zone_name):
        record_short = name[: -(len(zone_name) + 1)]
    else:
        print(f"  ! skipping {rtype} {name} — not inside zone {zone_name}", file=sys.stderr)
        return None

    # Skip routing policies we don't model yet.
    routing_policies = [k for k in ("Failover", "GeoLocation", "Region", "MultiValueAnswer") if k in rrset]
    if routing_policies:
        print(f"  ! skipping {rtype} {name} — unsupported routing policy: {routing_policies}", file=sys.stderr)
        return None

    base = {
        "zone_id": zone_id,
        "zone_name": zone_name,
        "record_short": record_short,
        "type": rtype,
    }

    if "AliasTarget" in rrset:
        at = rrset["AliasTarget"]
        base.update({
            "type": "ALIAS",   # our XRD flattens A/AAAA + alias into a single ALIAS type
            "alias_zone_id": at["HostedZoneId"],
            "alias_dns_name": at["DNSName"].rstrip("."),
            "alias_eval_target_health": at.get("EvaluateTargetHealth", False),
        })
    else:
        if "ResourceRecords" not in rrset:
            print(f"  ! skipping {rtype} {name} — no ResourceRecords nor AliasTarget", file=sys.stderr)
            return None
        base.update({
            "ttl": rrset.get("TTL", 300),
            "values": [r["Value"] for r in rrset["ResourceRecords"]],
        })

    if "SetIdentifier" in rrset:
        base["set_identifier"] = rrset["SetIdentifier"]
        # Weighted policy?
        if "Weight" in rrset:
            base["weight"] = rrset["Weight"]

    # Skip apex records — our templates assume non-apex for now.
    if base["record_short"] == "@":
        print(f"  ! skipping apex {rtype} in {zone_name} — apex records not yet supported", file=sys.stderr)
        return None

    return base


# ---------------------------------------------------------------------------
# Write helper — prints diff, writes on --write
# ---------------------------------------------------------------------------
class Writer:
    def __init__(self, write: bool):
        self.write = write
        self.created = 0
        self.skipped = 0

    def handle(self, path: Path, content: str, label: str) -> None:
        rel = path.relative_to(REPO_ROOT)
        if path.exists():
            print(f"  skip {rel} ({label}: already exists)")
            self.skipped += 1
            return
        print(f"  {'WRITE' if self.write else 'would write'}  {rel} ({label})")
        if self.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.created += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="actually create files (default: dry-run)")
    ap.add_argument("--filter", help="only import zones whose name contains this string")
    ap.add_argument("--domain", default=DEFAULTS["domain"])
    ap.add_argument("--subdomain", default=DEFAULTS["subdomain"])
    ap.add_argument("--system", default=DEFAULTS["system"])
    ap.add_argument("--environment", default=DEFAULTS["environment"])
    ap.add_argument("--aws-account-name", default=DEFAULTS["aws_account_name"])
    ap.add_argument("--aws-region", default=DEFAULTS["aws_region"])
    args = ap.parse_args()

    identity = get_caller_identity()
    ctx = {
        "domain": args.domain,
        "subdomain": args.subdomain,
        "system": args.system,
        "environment": args.environment,
        "aws_account_id": identity["Account"],
        "aws_account_name": args.aws_account_name,
        "aws_region": args.aws_region,
    }
    env_dir = REPO_ROOT / ENV_DIR_TMPL.format(**ctx)

    print(f"AWS Account : {ctx['aws_account_id']} ({ctx['aws_account_name']})")
    print(f"Target path : entities/environments/{ctx['domain']}/{ctx['subdomain']}/{ctx['system']}/{ctx['environment']}/resources/aws/")
    print(f"Mode        : {'WRITE' if args.write else 'DRY-RUN (use --write to apply)'}")
    print()

    writer = Writer(write=args.write)

    zones = list_hosted_zones()
    if args.filter:
        zones = [z for z in zones if args.filter in z["Name"]]
    if not zones:
        print("No zones match the filter. Nothing to do.")
        return 0

    for zone in zones:
        zone_name = zone["Name"].rstrip(".")
        zone_id = zone["Id"].split("/")[-1]
        print(f"\n=== Zone: {zone_name} ({zone_id}, {zone['ResourceRecordSetCount']} records) ===")

        # Zone XR + catalog entity
        zone_xr_path = env_dir / f"zone-{zone_name}.yaml"
        zone_xr_rel = str(zone_xr_path.relative_to(REPO_ROOT))
        writer.handle(zone_xr_path, zone_xr_yaml(ctx, zone_name, zone_id), "zone XR")
        writer.handle(CATALOG_ZONES_DIR / f"zone-{zone_name}.yaml",
                      zone_catalog_yaml(ctx, zone_name, zone_id, zone_xr_rel),
                      "zone catalog entity")

        # Records
        for rrset in list_record_sets(zone_id):
            rec = parse_record(rrset, zone_name, zone_id)
            if not rec:
                continue
            fqdn = f"{rec['record_short']}.{rec['zone_name']}"
            # Weighted records share fqdn — disambiguate by setIdentifier.
            suffix = ""
            if rec.get("set_identifier"):
                suffix = f"-{rec['set_identifier']}"
            rec["xr_name"] = f"record-{fqdn}{suffix}"
            rec_xr_path = env_dir / f"{rec['xr_name']}.yaml"
            rec_xr_rel = str(rec_xr_path.relative_to(REPO_ROOT))
            writer.handle(rec_xr_path, record_xr_yaml(ctx, rec), f"record XR [{rec['type']}]")
            writer.handle(CATALOG_RECORDS_DIR / f"{rec['xr_name']}.yaml",
                          record_catalog_yaml(ctx, rec, rec_xr_rel),
                          f"record catalog entity [{rec['type']}]")

    print()
    print(f"Summary: created {writer.created} files, skipped {writer.skipped}.")
    if not args.write and writer.created:
        print("Re-run with --write to actually create the files.")
        print("After --write: review, commit, push, open PR. Argo will sync and Crossplane will observe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
