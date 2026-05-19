#!/usr/bin/env python3
"""End-to-end test for the `spec.import.existing: true` path.

Validates the five invariants the Record composition must hold for an
imported (claim) record:

  1. XR Synced+Ready quickly with no Create attempt
  2. MR managementPolicies = [Observe, Update] (no Create, no Delete)
  3. AWS state is untouched on initial import (TTL + values preserved)
  4. Update path: XR mutation propagates to AWS via the Update path
  5. Delete behavior: deleting the XR does NOT delete the AWS record
     (ownership stays with the user)

Run:

    python3 lab/tests/e2e/record-import.py
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json as _json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_spec = _ilu.spec_from_file_location("all_scenarios", os.path.join(HERE, "all-scenarios.py"))
_all = _ilu.module_from_spec(_spec)
sys.modules["all_scenarios"] = _all
_spec.loader.exec_module(_all)  # type: ignore[attr-defined]

ZONE_NAME = _all.ZONE_NAME            # arthurbryan.com
PARENT_ZONE_ID = "Z03010981ALJFZB4QLU8W"
NAMESPACE = _all.NAMESPACE            # system-infrastructure-prd
step = _all.step
info = _all.info
ok = _all.ok
fail = _all.fail
run = _all.run
aws = _all.aws


def aws_get_record(fqdn: str, rtype: str = "A") -> list[dict]:
    fqdn_dot = fqdn if fqdn.endswith(".") else fqdn + "."
    out = aws("route53", "list-resource-record-sets",
              "--hosted-zone-id", PARENT_ZONE_ID,
              "--query", f"ResourceRecordSets[?Name=='{fqdn_dot}' && Type=='{rtype}']")
    return out if isinstance(out, list) else []


def aws_change(action: str, fqdn: str, rtype: str, ttl: int,
               values: list[str]) -> None:
    batch = {
        "Changes": [{
            "Action": action,
            "ResourceRecordSet": {
                "Name": fqdn,
                "Type": rtype,
                "TTL": ttl,
                "ResourceRecords": [{"Value": v} for v in values],
            },
        }],
    }
    aws("route53", "change-resource-record-sets",
        "--hosted-zone-id", PARENT_ZONE_ID,
        "--change-batch", _json.dumps(batch))


def wait_xr_ready(xr_name: str, deadline: int = 120) -> bool:
    elapsed = 0
    while elapsed < deadline:
        r = subprocess.run(
            ["kubectl", "-n", NAMESPACE, "get",
             f"record.dock.tech/{xr_name}", "-o", "json"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            obj = _json.loads(r.stdout)
            conds = {c["type"]: c["status"]
                     for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Synced") == "True" and conds.get("Ready") == "True":
                return True
        time.sleep(3)
        elapsed += 3
    return False


def wait_mr_atprovider_value(xr_name: str, expected_value: str,
                              deadline: int = 180) -> bool:
    elapsed = 0
    while elapsed < deadline:
        r = subprocess.run(
            ["kubectl", "-n", NAMESPACE, "get",
             f"record.route53.aws.m.upbound.io/{xr_name}",
             "-o", "jsonpath={.status.atProvider.records[0]}"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip() == expected_value:
            return True
        time.sleep(3)
        elapsed += 3
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default=time.strftime("%H%M%S"))
    args = ap.parse_args()

    record_name = f"import-test-{args.suffix}"
    fqdn = f"{record_name}.{ZONE_NAME}"
    xr_name = f"record-{fqdn}"

    failures = 0
    try:
        # ---- Setup: create the record manually in AWS (outside the platform).
        step(f"create AWS record {fqdn} via aws CLI (TTL=300, value=192.0.2.42)")
        aws_change("CREATE", fqdn, "A", 300, ["192.0.2.42"])
        ok("AWS record created")

        # ---- Apply XR with import.existing=true.
        step(f"apply Record XR with spec.import.existing=true")
        xr_yaml = f"""---
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: {xr_name}
  namespace: {NAMESPACE}
spec:
  name: {xr_name}
  domain: cross
  subdomain: cloud
  system: infrastructure
  environment: prd
  aws:
    account: 597230762851
    accountName: prd-account
  zoneId: {PARENT_ZONE_ID}
  zoneName: {ZONE_NAME}
  recordName: {record_name}
  type: A
  ttl: 300
  values:
    - 192.0.2.42
  import:
    existing: true
"""
        path = f"/tmp/import-xr-{args.suffix}.yaml"
        with open(path, "w") as f:
            f.write(xr_yaml)
        run(["kubectl", "apply", "-f", path])

        # ---- Invariant 1: XR Synced+Ready quickly.
        step("invariant 1: XR Synced+Ready within 60s (no Create attempted)")
        if not wait_xr_ready(xr_name, deadline=60):
            fail("XR did not reach Ready in 60s")
            failures += 1
        else:
            ok("XR Synced+Ready")

        # ---- Invariant 2: managementPolicies = [Observe, Update].
        step("invariant 2: MR managementPolicies = [Observe, Update]")
        mp = run([
            "kubectl", "-n", NAMESPACE, "get",
            f"record.route53.aws.m.upbound.io/{xr_name}",
            "-o", "jsonpath={.spec.managementPolicies}",
        ]).stdout.strip()
        if mp != '["Observe","Update"]':
            fail(f"managementPolicies={mp!r}; expected [\"Observe\",\"Update\"]")
            failures += 1
        else:
            ok(f"managementPolicies={mp}")

        # ---- Invariant 3: AWS state untouched.
        step("invariant 3: AWS state untouched (TTL=300, value=192.0.2.42)")
        rows = aws_get_record(fqdn)
        if not rows:
            fail("AWS record missing after import"); failures += 1
        else:
            r0 = rows[0]
            vals = sorted(rr["Value"] for rr in r0["ResourceRecords"])
            if r0.get("TTL") != 300 or vals != ["192.0.2.42"]:
                fail(f"AWS mutated: TTL={r0.get('TTL')} values={vals}")
                failures += 1
            else:
                ok("AWS record preserved")

        # ---- Invariant 4: Update path propagates.
        step("invariant 4: XR mutation flows through Update to AWS")
        run(["kubectl", "-n", NAMESPACE, "patch", "record.dock.tech", xr_name,
             "--type=merge", "-p",
             '{"spec":{"ttl":600,"values":["192.0.2.43"]}}'])
        if not wait_mr_atprovider_value(xr_name, "192.0.2.43", deadline=180):
            fail("MR atProvider did not pick up the new value in 3 min")
            failures += 1
        else:
            rows = aws_get_record(fqdn)
            r0 = rows[0]
            vals = sorted(rr["Value"] for rr in r0["ResourceRecords"])
            if r0.get("TTL") != 600 or vals != ["192.0.2.43"]:
                fail(f"AWS not updated: TTL={r0.get('TTL')} values={vals}")
                failures += 1
            else:
                ok("AWS updated to TTL=600 value=192.0.2.43")

        # ---- Invariant 5: Delete XR -> AWS record survives.
        step("invariant 5: deleting the XR must NOT delete the AWS record")
        run(["kubectl", "-n", NAMESPACE, "delete", "record.dock.tech", xr_name,
             "--wait=true", "--timeout=120s"])
        rows = aws_get_record(fqdn)
        if not rows:
            fail("AWS record was deleted along with the XR (ownership lost)")
            failures += 1
        else:
            ok("AWS record survived XR deletion (ownership preserved)")

    finally:
        # Always tear down the AWS-side record we created, regardless of
        # whether the XR delete left it or not.
        try:
            rows = aws_get_record(fqdn)
            if rows:
                r0 = rows[0]
                aws_change("DELETE", fqdn, "A", r0["TTL"],
                           [rr["Value"] for rr in r0["ResourceRecords"]])
                info("AWS record cleaned up")
        except Exception as e:
            info(f"AWS cleanup best-effort failed: {e}")

    print()
    print("=" * 60)
    if failures == 0:
        print("\033[0;32mSUMMARY: all 5 import invariants PASS\033[0m")
        return 0
    print(f"\033[0;31mSUMMARY: {failures} invariant(s) FAILED\033[0m")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
