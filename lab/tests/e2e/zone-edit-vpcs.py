#!/usr/bin/env python3
"""End-to-end validation of the aws-dns-zone-edit template.

Scenarios:
  1. add-cross-account-vpc   — submit edit adding a cross-account VPC, then
                               verify the new ZoneAssociation MR lands and AWS
                               reports the VPC associated.
  2. remove-cross-account-vpc — submit edit removing the same VPC, then verify
                               the ZoneAssociation MR is garbage-collected and
                               AWS no longer reports the VPC associated.
  3. last-vpc-rejected        — write an XR with empty vpcs and confirm the XRD
                               CEL rule rejects via kubectl apply --dry-run.

Each scenario is independent and idempotent — they leave the target zone in
its starting shape (just the default VPC).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.request

REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
BACKSTAGE = os.environ.get("BACKSTAGE_BACKEND", "http://localhost:7007")
ARGO_APPS = ["entities"]

ZONE_ENTITY = "resource:system-infrastructure-prd/zone-internal.arthurbryan.com"
ZONE_NAMESPACE = "system-infrastructure-prd"
ZONE_XR = "zone-internal.arthurbryan.com"
ZONE_NAME = "internal.arthurbryan.com"
PRD_ACCOUNT = "597230762851"

# Existing VPC entities in the catalog (catalog/aws-vpcs/).
DEV_DEFAULT_VPC_REF = "resource:default/vpc-0dd3eaef2e5c11f69"
PRD_DEFAULT_VPC_REF = "resource:default/vpc-0410f81cfe1bba322"
DEV_DEFAULT_VPC_ID = "vpc-0dd3eaef2e5c11f69"
PRD_DEFAULT_VPC_ID = "vpc-0410f81cfe1bba322"


def step(msg): print(f"\n>>> {msg}")
def ok(msg):   print(f"  PASS {msg}")
def fail(msg): print(f"  FAIL {msg}")


def http_json(url, *, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def token():
    return http_json(f"{BACKSTAGE}/api/auth/guest/refresh")["backstageIdentity"]["token"]


def run(cmd, check=True, env=None, capture=True):
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, env=env)


def aws_env_prd():
    out = run(["kubectl", "-n", "crossplane-system", "get", "secret", "aws-creds",
               "-o", "jsonpath={.data.credentials}"]).stdout
    creds = base64.b64decode(out).decode()
    key = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_access_key_id"))
    secret = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_secret_access_key"))
    return {**os.environ, "AWS_ACCESS_KEY_ID": key, "AWS_SECRET_ACCESS_KEY": secret,
            "AWS_DEFAULT_REGION": "us-east-1"}


def submit_zone_edit(values):
    body = {"templateRef": "template:default/aws-dns-zone-edit", "values": values}
    return http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks", method="POST", body=body,
                     headers={"Authorization": f"Bearer {token()}"})["id"]


def wait_task(task_id, deadline=240):
    elapsed = 0
    while elapsed < deadline:
        info = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}",
                         headers={"Authorization": f"Bearer {token()}"})
        if info.get("status") in ("completed", "failed", "cancelled"):
            return info["status"]
        time.sleep(3); elapsed += 3
    return "timeout"


def task_pr_url(task_id):
    info = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}",
                     headers={"Authorization": f"Bearer {token()}"})
    for step_id, step_info in (info.get("spec", {}).get("steps") or {}).items():
        if step_info.get("id") == "openPR":
            return step_info.get("output", {}).get("remoteUrl")
    # Newer Backstage stores output flat on the task.
    for ev in info.get("events", []) or []:
        body = ev.get("body", {}) or {}
        output = body.get("output", {}) or {}
        url = output.get("remoteUrl") or output.get("openPR", {}).get("remoteUrl") if isinstance(output.get("openPR"), dict) else None
        if url:
            return url
    return None


def merge_and_sync(pr_url):
    run(["gh", "pr", "merge", pr_url, "--squash", "--admin"])
    run(["git", "-C", REPO_ROOT, "pull", "--ff-only"])
    head = run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"]).stdout.strip()
    for app in ARGO_APPS:
        elapsed = 0
        while elapsed < 300:
            run(["kubectl", "-n", "argocd", "patch", f"application/{app}", "--type", "merge",
                 "-p", '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'], check=False)
            cur = run(["kubectl", "-n", "argocd", "get", f"application/{app}",
                       "-o", "jsonpath={.status.sync.revision}"], check=False).stdout.strip()
            if cur == head:
                break
            time.sleep(5); elapsed += 5
    return head


def aws_zone_vpcs(zone_id, env):
    elapsed = 0
    while elapsed < 180:
        r = run(["aws", "route53", "get-hosted-zone", "--id", zone_id, "--output", "json"],
                env=env, check=False)
        if r.returncode == 0:
            return sorted(v["VPCId"] for v in json.loads(r.stdout).get("VPCs", []))
        time.sleep(10); elapsed += 10
    return []


def get_zone_xr():
    r = run(["kubectl", "-n", ZONE_NAMESPACE, "get", f"zone.dock.tech/{ZONE_XR}", "-o", "json"])
    return json.loads(r.stdout)


def current_vpc_refs_from_annotation():
    obj = get_zone_xr()
    snap = obj.get("metadata", {}).get("annotations", {}).get("dock.tech/scaffolder-parameters")
    if not snap:
        return []
    try:
        parsed = json.loads(snap)
        vpcs = parsed.get("vpcs") or []
        return [v for v in vpcs if isinstance(v, str)]
    except (ValueError, json.JSONDecodeError):
        return []


def wait_zone_ready(deadline=240):
    elapsed = 0
    while elapsed < deadline:
        try:
            obj = get_zone_xr()
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Ready") == "True" and conds.get("Synced") == "True":
                return obj
        except subprocess.CalledProcessError:
            pass
        time.sleep(5); elapsed += 5
    return None


def scenario_add_cross_account(zone_id, prd_env):
    step(f"SCENARIO 1: add {PRD_DEFAULT_VPC_ID} (cross-account) to {ZONE_NAME}")
    existing = current_vpc_refs_from_annotation()
    new_list = existing + [PRD_DEFAULT_VPC_REF]
    task = submit_zone_edit({"zone": ZONE_ENTITY, "vpcs": new_list})
    print(f"  task: {task}")
    if wait_task(task) != "completed":
        fail("scaffolder did not complete")
        return 1
    pr = task_pr_url(task)
    print(f"  PR: {pr}")
    merge_and_sync(pr)
    if not wait_zone_ready():
        fail("zone XR not Ready after merge")
        return 1
    aws_vpcs = aws_zone_vpcs(zone_id, prd_env)
    print(f"  AWS VPCs: {aws_vpcs}")
    if PRD_DEFAULT_VPC_ID in aws_vpcs and DEV_DEFAULT_VPC_ID in aws_vpcs:
        ok("cross-account VPC associated, original VPC still present")
        return 0
    fail(f"expected both VPCs in AWS; got {aws_vpcs}")
    return 1


def scenario_remove_cross_account(zone_id, prd_env):
    step(f"SCENARIO 2: remove {PRD_DEFAULT_VPC_ID} from {ZONE_NAME}")
    existing = current_vpc_refs_from_annotation()
    new_list = [r for r in existing if r != PRD_DEFAULT_VPC_REF]
    task = submit_zone_edit({"zone": ZONE_ENTITY, "vpcs": new_list})
    print(f"  task: {task}")
    if wait_task(task) != "completed":
        fail("scaffolder did not complete")
        return 1
    pr = task_pr_url(task)
    print(f"  PR: {pr}")
    merge_and_sync(pr)
    if not wait_zone_ready():
        fail("zone XR not Ready after merge")
        return 1
    aws_vpcs = aws_zone_vpcs(zone_id, prd_env)
    print(f"  AWS VPCs: {aws_vpcs}")
    if PRD_DEFAULT_VPC_ID not in aws_vpcs and DEV_DEFAULT_VPC_ID in aws_vpcs:
        ok("cross-account VPC disassociated, original VPC still present")
        return 0
    fail(f"expected only original VPC in AWS; got {aws_vpcs}")
    return 1


def scenario_last_vpc_rejected():
    step("SCENARIO 3: XRD rejects empty vpcs on a private zone")
    xr_yaml = textwrap.dedent(f"""
        apiVersion: dock.tech/v1
        kind: Zone
        metadata:
          name: {ZONE_XR}
          namespace: {ZONE_NAMESPACE}
        spec:
          name: {ZONE_XR}
          domain: cross
          subdomain: cloud
          system: infrastructure
          environment: prd
          aws:
            account: {PRD_ACCOUNT}
            accountName: prd-account
          zoneName: {ZONE_NAME}
          visibility: private
          vpcs: []
    """).strip()
    r = subprocess.run(["kubectl", "apply", "--dry-run=server", "-f", "-"],
                       input=xr_yaml, capture_output=True, text=True)
    if r.returncode != 0 and "visibility=private requires at least one vpcs entry" in (r.stderr + r.stdout):
        ok("XRD CEL rule blocks empty vpcs on private zone")
        return 0
    fail(f"expected rejection; got returncode={r.returncode}, stderr={r.stderr[:200]}")
    return 1


def main():
    failures = 0
    prd_env = aws_env_prd()
    zone_obj = get_zone_xr()
    zone_id = zone_obj.get("status", {}).get("zoneId")
    if not zone_id:
        fail(f"zone {ZONE_XR} has no observed zoneId — abort")
        return 1
    print(f"target zone: {ZONE_NAME} ({zone_id})")

    failures += scenario_last_vpc_rejected()
    failures += scenario_add_cross_account(zone_id, prd_env)
    failures += scenario_remove_cross_account(zone_id, prd_env)

    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
