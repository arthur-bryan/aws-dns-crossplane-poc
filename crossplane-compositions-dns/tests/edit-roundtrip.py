#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
NC = "\033[0m"


def pass_line(label: str) -> None:
    print(f"[pass] {label}")


def fail_line(label: str, *, expected: Any = None, actual: Any = None, detail: str = "") -> None:
    print(f"[fail] {label}")
    if detail:
        print(f"       {detail}")
    if expected is not None:
        print(f"       expected: {expected}")
    if actual is not None:
        print(f"       actual:   {actual}")


def load_xr(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def write_yaml(obj: dict, path: Path) -> None:
    with path.open("w") as fh:
        yaml.safe_dump(obj, fh, default_flow_style=False, sort_keys=False)


def render(xr_path: Path, comp_path: Path, fn_path: Path) -> str:
    result = subprocess.run(
        ["crossplane", "render", str(xr_path), str(comp_path), str(fn_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"crossplane render failed for {xr_path}:\n{result.stderr}")
    return result.stdout


def split_yaml_docs(text: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(text) if d is not None]


def select_mr(docs: list[dict]) -> dict | None:
    for d in docs:
        if d.get("apiVersion") == "route53.aws.m.upbound.io/v1beta1":
            return d
    return None


def normalize_mr(doc: dict) -> dict:
    out = copy.deepcopy(doc)
    out.pop("status", None)
    md = out.setdefault("metadata", {})
    md.pop("ownerReferences", None)
    md.pop("creationTimestamp", None)
    md.pop("uid", None)
    md.pop("resourceVersion", None)
    md.pop("name", None)
    md.pop("namespace", None)
    md.pop("labels", None)
    annotations = md.get("annotations") or {}
    for k in list(annotations):
        if k.startswith("crossplane.io/composition-resource-name"):
            del annotations[k]
    if not annotations:
        md.pop("annotations", None)
    return out


def diff(a: Any, b: Any, path: str = "$") -> list[str]:
    if type(a) is not type(b):
        return [f"{path}: type mismatch ({type(a).__name__} vs {type(b).__name__})"]
    if isinstance(a, dict):
        diffs: list[str] = []
        for k in sorted(set(a.keys()) | set(b.keys())):
            if k not in a:
                diffs.append(f"{path}.{k}: only in reconstructed = {b[k]!r}")
            elif k not in b:
                diffs.append(f"{path}.{k}: only in original = {a[k]!r}")
            else:
                diffs.extend(diff(a[k], b[k], f"{path}.{k}"))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length differs (orig={len(a)}, recon={len(b)})"]
        diffs = []
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(diff(x, y, f"{path}[{i}]"))
        return diffs
    if a != b:
        return [f"{path}: {a!r} != {b!r}"]
    return []


ROUTING_FIELDS = {
    "weighted":     ["setIdentifier", "weight"],
    "failover":     ["setIdentifier", "failoverRoutingPolicy", "healthCheckId"],
    "latency":      ["setIdentifier", "latencyRoutingPolicy"],
    "geolocation":  ["setIdentifier", "geolocationRoutingPolicy"],
    "geoproximity": ["setIdentifier", "geoproximityRoutingPolicy"],
    "multivalue":   ["setIdentifier", "multivalueAnswerRoutingPolicy", "healthCheckId"],
}


def detect_routing_policy(spec: dict) -> str:
    if "weight" in spec:
        return "weighted"
    if "failoverRoutingPolicy" in spec:
        return "failover"
    if "latencyRoutingPolicy" in spec:
        return "latency"
    if "geolocationRoutingPolicy" in spec:
        return "geolocation"
    if "geoproximityRoutingPolicy" in spec:
        return "geoproximity"
    if spec.get("multivalueAnswerRoutingPolicy"):
        return "multivalue"
    return "simple"


def xr_to_params(spec: dict) -> dict:
    record_name = spec.get("recordName") or ""
    rtype = spec["type"]
    zone_ref = (
        f"resource:system-{spec['system']}-{spec['environment']}"
        f"/zone-{spec['zoneName']}"
    )
    p: dict[str, Any] = {
        "zone": zone_ref,
        "recordName": record_name,
        "type": rtype,
    }
    if rtype == "ALIAS":
        at = spec.get("aliasTarget", {})
        p["serviceType"] = at["serviceType"]
        p["dnsName"] = at["dnsName"]
        p["evaluateTargetHealth"] = bool(at.get("evaluateTargetHealth", False))
        target_region = at.get("region") or spec.get("aws", {}).get("region")
        if target_region:
            p["targetRegion"] = target_region
        if at["serviceType"] == "Custom" and "hostedZoneId" in at:
            p["customZoneId"] = at["hostedZoneId"]
    else:
        p["ttl"] = spec["ttl"]
        p["values"] = list(spec["values"])

    policy = detect_routing_policy(spec)
    p["routingPolicy"] = policy
    if policy == "weighted":
        p["setIdentifier"] = spec["setIdentifier"]
        p["weight"] = spec["weight"]
    elif policy == "failover":
        p["setIdentifier"] = spec["setIdentifier"]
        p["failoverType"] = spec["failoverRoutingPolicy"]["type"]
        if "healthCheckId" in spec:
            p["healthCheckId"] = spec["healthCheckId"]
    elif policy == "latency":
        p["setIdentifier"] = spec["setIdentifier"]
        p["latencyRegion"] = spec["latencyRoutingPolicy"]["region"]
    elif policy == "geolocation":
        p["setIdentifier"] = spec["setIdentifier"]
        geo = spec["geolocationRoutingPolicy"]
        if "continent" in geo:
            p["geoContinent"] = geo["continent"]
        if "country" in geo:
            p["geoCountry"] = geo["country"]
        if "subdivision" in geo:
            p["geoSubdivision"] = geo["subdivision"]
    elif policy == "geoproximity":
        p["setIdentifier"] = spec["setIdentifier"]
        gp = spec["geoproximityRoutingPolicy"]
        if "awsRegion" in gp:
            p["geoproxAwsRegion"] = gp["awsRegion"]
        if "coordinates" in gp:
            p["geoproxLatitude"] = gp["coordinates"]["latitude"]
            p["geoproxLongitude"] = gp["coordinates"]["longitude"]
        if "bias" in gp:
            p["geoproxBias"] = gp["bias"]
    elif policy == "multivalue":
        p["setIdentifier"] = spec["setIdentifier"]
        if "healthCheckId" in spec:
            p["healthCheckId"] = spec["healthCheckId"]
    return p


def compute_key(record_name: str, rtype: str) -> str:
    return record_name if record_name else f"apex-{rtype.lower()}"


def params_to_xr(params: dict, zone_meta: dict) -> dict:
    key = compute_key(params["recordName"], params["type"])
    xr_name = f"record-{key}.{zone_meta['zoneName']}"
    spec: dict[str, Any] = {
        "name": xr_name,
        "domain": zone_meta["domain"],
        "subdomain": zone_meta["subdomain"],
        "system": zone_meta["system"],
        "environment": zone_meta["environment"],
        "aws": {
            "account": int(zone_meta["awsAccount"]),
            "accountName": zone_meta["awsAccountName"],
        },
        "zoneId": zone_meta["zoneId"],
        "zoneName": zone_meta["zoneName"],
        "recordName": params["recordName"],
        "type": params["type"],
    }
    if params["type"] == "ALIAS":
        alias: dict[str, Any] = {
            "serviceType": params["serviceType"],
            "dnsName": params["dnsName"],
            "evaluateTargetHealth": params.get("evaluateTargetHealth", False),
        }
        if params.get("targetRegion"):
            alias["region"] = params["targetRegion"]
        if params["serviceType"] == "Custom" and params.get("customZoneId"):
            alias["hostedZoneId"] = params["customZoneId"]
        spec["aliasTarget"] = alias
    else:
        spec["ttl"] = params["ttl"]
        spec["values"] = list(params["values"])

    policy = params.get("routingPolicy", "simple")
    if policy == "weighted":
        spec["setIdentifier"] = params["setIdentifier"]
        spec["weight"] = params["weight"]
    elif policy == "failover":
        spec["setIdentifier"] = params["setIdentifier"]
        spec["failoverRoutingPolicy"] = {"type": params["failoverType"]}
        if params.get("healthCheckId"):
            spec["healthCheckId"] = params["healthCheckId"]
    elif policy == "latency":
        spec["setIdentifier"] = params["setIdentifier"]
        spec["latencyRoutingPolicy"] = {"region": params["latencyRegion"]}
    elif policy == "geolocation":
        spec["setIdentifier"] = params["setIdentifier"]
        geo: dict[str, Any] = {}
        if params.get("geoContinent"):
            geo["continent"] = params["geoContinent"]
        if params.get("geoCountry"):
            geo["country"] = params["geoCountry"]
        if params.get("geoSubdivision"):
            geo["subdivision"] = params["geoSubdivision"]
        spec["geolocationRoutingPolicy"] = geo
    elif policy == "geoproximity":
        spec["setIdentifier"] = params["setIdentifier"]
        gp: dict[str, Any] = {}
        if params.get("geoproxAwsRegion"):
            gp["awsRegion"] = params["geoproxAwsRegion"]
        if "geoproxLatitude" in params and "geoproxLongitude" in params:
            gp["coordinates"] = {
                "latitude": params["geoproxLatitude"],
                "longitude": params["geoproxLongitude"],
            }
        if params.get("geoproxBias"):
            gp["bias"] = params["geoproxBias"]
        spec["geoproximityRoutingPolicy"] = gp
    elif policy == "multivalue":
        spec["setIdentifier"] = params["setIdentifier"]
        spec["multivalueAnswerRoutingPolicy"] = True
        if params.get("healthCheckId"):
            spec["healthCheckId"] = params["healthCheckId"]

    return {
        "apiVersion": "dock.tech/v1",
        "kind": "Record",
        "metadata": {
            "name": xr_name,
            "namespace": f"system-{zone_meta['system']}-{zone_meta['environment']}",
        },
        "spec": spec,
    }


def zone_meta_from_xr(xr: dict) -> dict:
    spec = xr["spec"]
    return {
        "zoneName": spec["zoneName"],
        "zoneId": spec.get("zoneId", ""),
        "domain": spec["domain"],
        "subdomain": spec["subdomain"],
        "system": spec["system"],
        "environment": spec["environment"],
        "awsAccount": str(spec["aws"]["account"]),
        "awsAccountName": spec["aws"]["accountName"],
    }


def is_record_xr(xr: dict) -> bool:
    return xr.get("kind") == "Record" and xr.get("apiVersion", "").startswith("dock.tech/")


def is_import_mode(xr: dict) -> bool:
    return bool(xr.get("spec", {}).get("import", {}).get("existing"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xrs-dir", required=True, type=Path)
    ap.add_argument("--record-composition", required=True, type=Path)
    ap.add_argument("--functions", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)

    fixtures = sorted(args.xrs_dir.glob("record-*.yaml"))
    if not fixtures:
        print("[fail] no record-*.yaml fixtures discovered", file=sys.stdout)
        return 1

    failures = 0
    for path in fixtures:
        xr = load_xr(path)
        if not is_record_xr(xr):
            continue
        label = path.stem
        if is_import_mode(xr):
            print(f"[skip] {label} (import mode)")
            continue
        try:
            params = xr_to_params(xr["spec"])
            zone_meta = zone_meta_from_xr(xr)
            reconstructed = params_to_xr(params, zone_meta)
            json.dumps(params)
        except Exception as exc:
            failures += 1
            fail_line(label, detail=f"forward/inverse failed: {exc}")
            continue

        recon_path = args.work_dir / f"{label}.reconstructed.yaml"
        write_yaml(reconstructed, recon_path)

        try:
            orig_render = render(path, args.record_composition, args.functions)
            recon_render = render(recon_path, args.record_composition, args.functions)
        except RuntimeError as exc:
            failures += 1
            fail_line(label, detail=str(exc).splitlines()[0])
            continue

        orig_mr = select_mr(split_yaml_docs(orig_render))
        recon_mr = select_mr(split_yaml_docs(recon_render))
        if orig_mr is None or recon_mr is None:
            failures += 1
            fail_line(label, detail="no MR doc in render output")
            continue

        diffs = diff(normalize_mr(orig_mr), normalize_mr(recon_mr))
        if not diffs:
            pass_line(label)
        else:
            failures += 1
            fail_line(label, detail="rendered MR differs after round-trip")
            for d in diffs:
                print(f"       {d}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
