#!/usr/bin/env python3
"""Patch dock.tech/zone-id into catalog Zone entities once Crossplane reports it.

Reads every Zone XR in the cluster, finds the matching
entities/catalog/<env>/<zoneName>/zone.yaml file, and inserts or updates
the dock.tech/zone-id annotation with the value from status.zoneId. The
annotation is only known after the Route53 zone is created, so the
scaffolder cannot emit it directly; this reconciler closes the loop.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_DIR = REPO_ROOT / "entities" / "catalog"

ANNOTATION_KEY = "dock.tech/zone-id"
ANCHOR_KEY = "dock.tech/zone-name"


def kubectl_zones() -> list[dict]:
    result = subprocess.run(
        ["kubectl", "get", "zone.dock.tech", "--all-namespaces", "-o", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.exit(f"kubectl error: {result.stderr}")
    return json.loads(result.stdout or "{}").get("items", [])


def candidate_paths(env: str, zone_name: str) -> list[Path]:
    paths = [CATALOG_DIR / env / zone_name / "zone.yaml"]
    if not paths[0].exists():
        paths.extend(CATALOG_DIR.rglob("zone.yaml"))
    return paths


def find_catalog_file(xr_name: str, env: str, zone_name: str) -> Path | None:
    direct = CATALOG_DIR / env / zone_name / "zone.yaml"
    if direct.exists():
        return direct
    for path in CATALOG_DIR.rglob("zone.yaml"):
        text = path.read_text()
        m = re.search(r"^\s*name:\s*(\S+)\s*$", text, re.MULTILINE)
        if m and m.group(1) == xr_name:
            return path
    return None


def patch_zone_id(text: str, zone_id: str) -> tuple[str, str]:
    """Return (new_text, action) where action is 'updated', 'inserted', or 'unchanged'."""
    existing = re.search(
        rf"^(\s*){re.escape(ANNOTATION_KEY)}:\s*(.*?)\s*$",
        text, re.MULTILINE,
    )
    if existing:
        current = existing.group(2).strip().strip('"')
        if current == zone_id:
            return text, "unchanged"
        new_line = f"{existing.group(1)}{ANNOTATION_KEY}: {zone_id}"
        return text[:existing.start()] + new_line + text[existing.end():], "updated"

    anchor = re.search(
        rf"^(\s*){re.escape(ANCHOR_KEY)}:\s*\S+.*$",
        text, re.MULTILINE,
    )
    if not anchor:
        return text, "no-anchor"
    indent = anchor.group(1)
    insert_at = anchor.end()
    new_line = f"\n{indent}{ANNOTATION_KEY}: {zone_id}"
    return text[:insert_at] + new_line + text[insert_at:], "inserted"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    zones = kubectl_zones()
    print(f"scanning {len(zones)} Zone XR(s)")

    changed = 0
    skipped = 0
    missing = 0
    for xr in zones:
        meta = xr.get("metadata", {})
        spec = xr.get("spec", {})
        status = xr.get("status", {})
        xr_name = meta.get("name", "")
        env = spec.get("environment", "")
        zone_name = spec.get("zoneName", "")
        zone_id = status.get("zoneId")
        label = f"{xr_name} (env={env}, zoneName={zone_name})"

        if not zone_id:
            print(f"  skip   {label}: no status.zoneId yet")
            skipped += 1
            continue

        path = find_catalog_file(xr_name, env, zone_name)
        if not path:
            print(f"  MISS   {label}: no catalog file found")
            missing += 1
            continue

        text = path.read_text()
        new_text, action = patch_zone_id(text, zone_id)
        rel = path.relative_to(REPO_ROOT)
        if action == "unchanged":
            print(f"  skip   {label}: zone-id already {zone_id} in {rel}")
            skipped += 1
            continue
        if action == "no-anchor":
            print(f"  MISS   {label}: anchor {ANCHOR_KEY} not in {rel}")
            missing += 1
            continue
        if not args.write:
            print(f"  DRY    {label}: would {action} zone-id={zone_id} in {rel}")
        else:
            path.write_text(new_text)
            print(f"  WRITE  {label}: {action} zone-id={zone_id} in {rel}")
        changed += 1

    print()
    print(f"summary: {changed} changed, {skipped} unchanged, {missing} missing")
    if not args.write and changed:
        print("re-run with --write to apply.")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
