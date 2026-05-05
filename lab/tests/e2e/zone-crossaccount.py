#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
BACKSTAGE = os.environ.get("BACKSTAGE_BACKEND", "http://localhost:7007")
ARGO_APPS = ["entities", "lab-root", "crossplane-compositions-dns"]

PARENT_ENTITY = "resource:system-infrastructure-prd/zone-arthurbryan.com"
PARENT_ZONE = "arthurbryan.com"
PARENT_ZONE_ID = "Z03010981ALJFZB4QLU8W"
PRD_ACCOUNT_ID = "597230762851"
DEV_ACCOUNT_ID = "309670275661"
DEV_ASSUME_ROLE_ARN = f"arn:aws:iam::{DEV_ACCOUNT_ID}:role/OrganizationAccountAccessRole"

PREFIX = "crossacct-test"
ENV = "dev"
CHILD_ZONE = f"{PREFIX}.{PARENT_ZONE}"
CHILD_NAMESPACE = "system-infrastructure-dev"
CHILD_XR = f"zone-{CHILD_ZONE}"

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

def run(cmd, check=True, capture=True, env=None):
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, env=env)

def step(msg):
    print(f"\n>>> {msg}")

def ok(msg):
    print(f"  PASS  {msg}")

def fail(msg):
    print(f"  FAIL  {msg}")

def aws_env_prd():
    creds_b64 = run(["kubectl", "-n", "crossplane-system", "get", "secret", "aws-creds",
                     "-o", "jsonpath={.data.credentials}"]).stdout
    import base64
    creds = base64.b64decode(creds_b64).decode()
    key = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_access_key_id"))
    secret = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_secret_access_key"))
    return {**os.environ, "AWS_ACCESS_KEY_ID": key, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "us-east-1"}

def aws_env_dev():
    base = aws_env_prd()
    r = run(["aws", "sts", "assume-role",
             "--role-arn", DEV_ASSUME_ROLE_ARN,
             "--role-session-name", "e2e-crossacct",
             "--output", "json"], env=base)
    creds = json.loads(r.stdout)["Credentials"]
    return {**base,
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"]}

def aws(args, env):
    return run(["aws", *args, "--output", "json"], env=env, check=False)

def submit_form():
    values = {
        "delegatedZone": PARENT_ENTITY,
        "prefix": PREFIX,
        "environment": ENV,
        "private": False,
        "deletionProtection": False,
    }
    body = {"templateRef": "template:default/aws-dns-zone", "values": values}
    resp = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks", method="POST", body=body,
        headers={"Authorization": f"Bearer {token()}"},
    )
    return resp["id"]

def wait_task(task_id, deadline=240):
    elapsed = 0
    while elapsed < deadline:
        info = http_json(
            f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token()}"},
        )
        if info.get("status") in ("completed", "failed", "cancelled"):
            return info["status"]
        time.sleep(3)
        elapsed += 3
    return "timeout"

def task_pr_url(task_id):
    events = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
        headers={"Authorization": f"Bearer {token()}"},
    ) or []
    for ev in events:
        if ev.get("type") != "completion":
            continue
        out = (ev.get("body") or {}).get("output") or {}
        for link in out.get("links") or []:
            if link.get("url"):
                return link["url"]
    return None

def task_log_tail(task_id, n=30):
    events = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
        headers={"Authorization": f"Bearer {token()}"},
    ) or []
    msgs = []
    for ev in events:
        body = ev.get("body") or {}
        msg = body.get("message")
        if msg:
            msgs.append(f"  [{ev.get('type')}] {body.get('stepId') or '-'}: {msg.strip().splitlines()[0][:200]}")
    return msgs[-n:]

def merge_pr(pr_url):
    pr_num = pr_url.rstrip("/").split("/")[-1]
    run(["gh", "pr", "merge", pr_num, "--merge", "--delete-branch"], capture=False)

def git_pull_head():
    run(["git", "-C", REPO_ROOT, "fetch", "--quiet", "origin"])
    run(["git", "-C", REPO_ROOT, "pull", "--ff-only", "--quiet"])
    return run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"]).stdout.strip()

def argo_wait(app, revision, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        run(["kubectl", "-n", "argocd", "patch", f"application/{app}", "--type", "merge",
             "-p", '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'],
            check=False, capture=True)
        cur = run(["kubectl", "-n", "argocd", "get", f"application/{app}",
                   "-o", "jsonpath={.status.sync.revision}"], check=False).stdout.strip()
        if cur == revision:
            return True
        time.sleep(5)
        elapsed += 5
    return False

def wait_zone_ready(name, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        r = run(["kubectl", "-n", CHILD_NAMESPACE, "get", f"zone.dock.tech/{name}", "-o", "json"], check=False)
        if r.returncode == 0:
            obj = json.loads(r.stdout)
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Ready") == "True" and conds.get("Synced") == "True":
                return obj
        time.sleep(5)
        elapsed += 5
    return None

def find_delegation_mr(child_zone_name):
    r = run(["kubectl", "-n", CHILD_NAMESPACE, "get", "record.route53.aws.m.upbound.io",
             "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    for it in json.loads(r.stdout).get("items", []):
        s = it.get("spec", {}).get("forProvider", {})
        if s.get("type") == "NS" and s.get("name") == child_zone_name:
            return it
    return None

def main():
    failures = 0

    step(f"submit form (env={ENV}, parent={PARENT_ZONE}, prefix={PREFIX})")
    task_id = submit_form()
    print(f"  task: {task_id}")
    status = wait_task(task_id)
    print(f"  status: {status}")
    for line in task_log_tail(task_id, 25):
        print(line)
    if status != "completed":
        fail("scaffolder task did not complete")
        return 1
    pr = task_pr_url(task_id)
    print(f"  PR: {pr}")
    ok("scaffolder task completed and PR opened")

    step("merge PR + wait Argo sync")
    merge_pr(pr)
    head = git_pull_head()
    print(f"  HEAD: {head[:12]}")
    for app in ARGO_APPS:
        if not argo_wait(app, head):
            fail(f"argo {app} did not sync")
            failures += 1
    ok("Argo synced")

    step(f"verify Zone XR {CHILD_XR} ready")
    obj = wait_zone_ready(CHILD_XR)
    if not obj:
        fail("Zone XR absent or not Ready")
        return 1
    spec = obj["spec"]
    print(f"  spec.environment: {spec.get('environment')}")
    print(f"  spec.aws: {spec.get('aws')}")
    print(f"  spec.delegatedFromZoneId: {spec.get('delegatedFromZoneId')}")
    print(f"  spec.delegatedFromAccountName: {spec.get('delegatedFromAccountName')}")
    print(f"  status.zoneId: {obj.get('status',{}).get('zoneId')}")
    print(f"  status.nameServers: {obj.get('status',{}).get('nameServers')}")

    if spec.get("environment") != "dev":
        fail("XR.spec.environment != dev"); failures += 1
    if spec.get("aws", {}).get("accountName") != "dev-account":
        fail("XR.spec.aws.accountName != dev-account"); failures += 1
    if str(spec.get("aws", {}).get("account")) != DEV_ACCOUNT_ID:
        fail(f"XR.spec.aws.account != {DEV_ACCOUNT_ID}"); failures += 1
    if spec.get("delegatedFromZoneId") != PARENT_ZONE_ID:
        fail("XR.spec.delegatedFromZoneId mismatch"); failures += 1
    if spec.get("delegatedFromAccountName") != "prd-account":
        fail("XR.spec.delegatedFromAccountName != prd-account"); failures += 1
    if failures == 0:
        ok("XR fields all correct")

    step("verify Zone MR providerConfigRef = dev-account")
    mr = run(["kubectl", "-n", CHILD_NAMESPACE, "get", f"zone.route53.aws.m.upbound.io/{CHILD_XR}", "-o", "json"], check=False)
    if mr.returncode != 0:
        fail("Zone MR absent"); return 1
    mrobj = json.loads(mr.stdout)
    pc = mrobj.get("spec", {}).get("providerConfigRef", {}).get("name")
    print(f"  Zone MR providerConfigRef.name: {pc}")
    if pc != "dev-account":
        fail("Zone MR not using dev-account"); failures += 1
    else:
        ok("Zone MR uses dev-account")

    step("verify NS delegation MR providerConfigRef = prd-account")
    deleg = None
    elapsed = 0
    while elapsed < 180 and deleg is None:
        deleg = find_delegation_mr(CHILD_ZONE)
        if deleg is None:
            time.sleep(5); elapsed += 5
    if not deleg:
        fail(f"NS delegation MR not found"); return 1
    pc_d = deleg.get("spec", {}).get("providerConfigRef", {}).get("name")
    print(f"  delegation MR providerConfigRef.name: {pc_d}")
    if pc_d != "prd-account":
        fail("delegation MR not using prd-account"); failures += 1
    dconds = {c["type"]: c["status"] for c in deleg.get("status", {}).get("conditions") or []}
    if dconds.get("Ready") != "True":
        fail("delegation MR not Ready"); failures += 1
    else:
        ok("delegation MR Ready and uses prd-account")

    step(f"verify Route53 zone exists in DEV account ({DEV_ACCOUNT_ID})")
    dev_env = aws_env_dev()
    zones = aws(["route53", "list-hosted-zones", "--query",
                 f"HostedZones[?Name==`{CHILD_ZONE}.`]"], env=dev_env)
    items = json.loads(zones.stdout) if zones.returncode == 0 else []
    print(f"  found {len(items)} zone(s) named {CHILD_ZONE} in dev account")
    if items:
        for z in items:
            print(f"    {z['Id']}  Name={z['Name']}  Private={z['Config']['PrivateZone']}")
    if not items:
        fail("zone not found in dev account"); failures += 1
    else:
        ok(f"zone exists in dev account")

    step("verify zone DOES NOT exist in PRD account (no leak)")
    prd_env = aws_env_prd()
    zones_prd = aws(["route53", "list-hosted-zones", "--query",
                     f"HostedZones[?Name==`{CHILD_ZONE}.`]"], env=prd_env)
    items_prd = json.loads(zones_prd.stdout) if zones_prd.returncode == 0 else []
    print(f"  found {len(items_prd)} zone(s) named {CHILD_ZONE} in prd account")
    if items_prd:
        fail("zone leaked into prd account"); failures += 1
    else:
        ok("no leak into prd")

    step(f"verify NS record in parent zone {PARENT_ZONE} (in prd account)")
    rrs = aws(["route53", "list-resource-record-sets",
               "--hosted-zone-id", PARENT_ZONE_ID,
               "--query", f"ResourceRecordSets[?Type==`NS` && Name==`{CHILD_ZONE}.`]"], env=prd_env)
    rrs_items = json.loads(rrs.stdout) if rrs.returncode == 0 else []
    print(f"  found {len(rrs_items)} NS record(s) for {CHILD_ZONE} in parent zone")
    if rrs_items:
        for r in rrs_items:
            print(f"    Records: {[v['Value'] for v in r.get('ResourceRecords', [])]}")
    expected_ns = sorted(obj.get("status", {}).get("nameServers") or [])
    actual_ns = sorted(v["Value"] for r in rrs_items for v in r.get("ResourceRecords", []))
    print(f"  expected (XR.status): {expected_ns}")
    print(f"  actual   (parent NS): {actual_ns}")
    expected_normalized = [n.rstrip(".") for n in expected_ns]
    actual_normalized = [n.rstrip(".") for n in actual_ns]
    if expected_normalized != actual_normalized:
        fail("parent NS record does not match child nameservers"); failures += 1
    else:
        ok("parent NS delegation matches child")

    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
