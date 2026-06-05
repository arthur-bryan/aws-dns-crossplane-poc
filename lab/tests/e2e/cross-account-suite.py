#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
BACKSTAGE = os.environ.get("BACKSTAGE_BACKEND", "http://localhost:7007")
ARGO_APPS = ["entities", "lab-root", "crossplane-compositions-dns"]

PRD_ACCOUNT = "597230762851"
DEV_ACCOUNT = "309670275661"
DEV_ASSUME_ROLE = f"arn:aws:iam::{DEV_ACCOUNT}:role/OrganizationAccountAccessRole"

PARENT_PRD = "resource:system-infrastructure-prd/zone-arthurbryan.com"
PARENT_DEV = "resource:system-infrastructure-dev/zone-crossacct-test.arthurbryan.com"
PARENT_PRD_ZONE = "arthurbryan.com"
PARENT_DEV_ZONE = "crossacct-test.arthurbryan.com"
PARENT_PRD_ZONEID = "Z03010981ALJFZB4QLU8W"

DEV_VPC_REF = "resource:default/vpc-0dd3eaef2e5c11f69"
PRD_VPC_REF = "resource:default/vpc-0410f81cfe1bba322"
DEV_VPC_ID = "vpc-0dd3eaef2e5c11f69"
PRD_VPC_ID = "vpc-0410f81cfe1bba322"

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
    out = run(["kubectl", "-n", "crossplane-system", "get", "secret", "aws-creds",
               "-o", "jsonpath={.data.credentials}"]).stdout
    creds = base64.b64decode(out).decode()
    key = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_access_key_id"))
    secret = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_secret_access_key"))
    return {**os.environ, "AWS_ACCESS_KEY_ID": key, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "us-east-1"}

def aws_env_dev():
    base = aws_env_prd()
    r = run(["aws", "sts", "assume-role", "--role-arn", DEV_ASSUME_ROLE,
             "--role-session-name", "e2e-suite", "--output", "json"], env=base)
    creds = json.loads(r.stdout)["Credentials"]
    return {**base,
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"]}

def aws(args, env):
    return run(["aws", *args, "--output", "json"], env=env, check=False)

def submit(template_ref, values):
    body = {"templateRef": template_ref, "values": values}
    resp = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks", method="POST", body=body,
                     headers={"Authorization": f"Bearer {token()}"})
    return resp["id"]

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
    events = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
                       headers={"Authorization": f"Bearer {token()}"}) or []
    for ev in events:
        if ev.get("type") != "completion":
            continue
        out = (ev.get("body") or {}).get("output") or {}
        for link in out.get("links") or []:
            if link.get("url"):
                return link["url"]
    return None

def task_log_tail(task_id, n=20):
    events = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
                       headers={"Authorization": f"Bearer {token()}"}) or []
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
        time.sleep(5); elapsed += 5
    return False

def submit_pr_merge_sync(template_ref, values, label):
    print(f"  submitting form: {label}")
    task_id = submit(template_ref, values)
    print(f"  task: {task_id}")
    status = wait_task(task_id)
    print(f"  status: {status}")
    if status != "completed":
        for line in task_log_tail(task_id, 30):
            print(line)
        return None, "task did not complete"
    pr = task_pr_url(task_id)
    if not pr:
        return None, "no PR url"
    print(f"  PR: {pr}")
    merge_pr(pr)
    head = git_pull_head()
    print(f"  HEAD: {head[:12]}")
    for app in ARGO_APPS:
        if not argo_wait(app, head):
            return None, f"argo {app} did not sync"
    return head, None

def get_xr(kind_namespace, kind_resource, name):
    r = run(["kubectl", "-n", kind_namespace, "get", f"{kind_resource}/{name}", "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)

def wait_ready(namespace, kind_resource, name, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        obj = get_xr(namespace, kind_resource, name)
        if obj:
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Synced") == "True" and conds.get("Ready") == "True":
                return obj
        time.sleep(5); elapsed += 5
    return get_xr(namespace, kind_resource, name)

def find_mr(namespace, kind_plural, predicate):
    r = run(["kubectl", "-n", namespace, "get", kind_plural, "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    for it in json.loads(r.stdout).get("items", []):
        if predicate(it):
            return it
    return None

def test_a_parent_in_dev():
    step("Test A: parent in dev, child in dev (sub-of-sub)")
    head, err = submit_pr_merge_sync(
        "template:default/dns-zone",
        {
            "delegatedZone": PARENT_DEV,
            "prefix": "sub",
            "environment": "dev",
            "private": False,
            "deletionProtection": False,
        },
        "sub.crossacct-test.arthurbryan.com (env=dev)",
    )
    if err:
        fail(err); return 1
    failures = 0

    xr_name = "zone-sub.crossacct-test.arthurbryan.com"
    obj = wait_ready("system-infrastructure-dev", "zone.dock.tech", xr_name)
    if not obj:
        fail("zone XR absent"); return 1
    spec = obj["spec"]
    print(f"  spec.aws: {spec.get('aws')}")
    print(f"  spec.delegatedFromAccountName: {spec.get('delegatedFromAccountName')}")
    print(f"  spec.delegatedFromZoneId: {spec.get('delegatedFromZoneId')}")
    if spec.get("aws", {}).get("accountName") != "dev-account":
        fail("child zone not in dev-account"); failures += 1
    if spec.get("delegatedFromAccountName") != "dev-account":
        fail("delegatedFromAccountName != dev-account"); failures += 1
    if failures == 0:
        ok("XR fields correct (parent and child both dev-account)")

    deleg = find_mr("system-infrastructure-dev", "record.route53.aws.m.upbound.io",
                    lambda it: it.get("spec", {}).get("forProvider", {}).get("type") == "NS"
                               and it["spec"]["forProvider"].get("name") == "sub.crossacct-test.arthurbryan.com")
    if not deleg:
        fail("delegation MR not found"); return 1
    pc = deleg["spec"]["providerConfigRef"]["name"]
    print(f"  delegation MR providerConfigRef: {pc}")
    if pc != "dev-account":
        fail("delegation MR not using dev-account (parent's account)"); failures += 1
    else:
        ok("delegation MR uses dev-account (parent's account)")

    dev_env = aws_env_dev()
    rrs = aws(["route53", "list-resource-record-sets",
               "--hosted-zone-id", obj.get("status", {}).get("zoneId", ""),
               "--query", "ResourceRecordSets[?Type==`SOA`]"], env=dev_env)
    items = json.loads(rrs.stdout) if rrs.returncode == 0 else []
    if items:
        ok("child zone exists in dev account (SOA observable)")
    else:
        fail("child zone not visible in dev account"); failures += 1

    return failures

def test_b_record_against_dev_zone():
    step("Test B: record on a scaffolder-built dev zone")
    head, err = submit_pr_merge_sync(
        "template:default/dns-record",
        {
            "zone": PARENT_DEV,
            "recordName": "app",
            "type": "A",
            "ttl": 300,
            "values": ["10.0.99.1"],
            "routingPolicy": "simple",
        },
        "A app.crossacct-test.arthurbryan.com -> 10.0.99.1 (in dev)",
    )
    if err:
        fail(err); return 1
    failures = 0

    xr_name = "record-app.crossacct-test.arthurbryan.com"
    obj = wait_ready("system-infrastructure-dev", "record.dock.tech", xr_name)
    if not obj:
        fail("record XR absent"); return 1
    spec = obj["spec"]
    print(f"  spec.aws.accountName: {spec.get('aws', {}).get('accountName')}")
    print(f"  spec.zoneId: {spec.get('zoneId')}")
    if spec.get("aws", {}).get("accountName") != "dev-account":
        fail("record XR not using dev-account"); failures += 1

    mr = run(["kubectl", "-n", "system-infrastructure-dev", "get",
              f"record.route53.aws.m.upbound.io/{xr_name}", "-o", "json"], check=False)
    if mr.returncode != 0:
        fail("record MR absent"); return 1
    mrobj = json.loads(mr.stdout)
    pc = mrobj.get("spec", {}).get("providerConfigRef", {}).get("name")
    print(f"  record MR providerConfigRef: {pc}")
    if pc != "dev-account":
        fail("record MR not using dev-account"); failures += 1
    else:
        ok("record MR uses dev-account")

    dev_env = aws_env_dev()
    fqdn = "app.crossacct-test.arthurbryan.com."
    rrs = aws(["route53", "list-resource-record-sets",
               "--hosted-zone-id", spec["zoneId"],
               "--query", f"ResourceRecordSets[?Type==`A`&&Name==`{fqdn}`]"], env=dev_env)
    items = json.loads(rrs.stdout) if rrs.returncode == 0 else []
    print(f"  found {len(items)} A record(s) in dev account zone")
    if items and any(v["Value"] == "10.0.99.1" for r in items for v in r.get("ResourceRecords", [])):
        ok("Route53 A record present in dev account with correct value")
    else:
        fail("A record missing or wrong value"); failures += 1

    return failures

def test_c_cross_account_private_zone():
    step("Test C: private zone in dev with cross-account VPC from prd")
    head, err = submit_pr_merge_sync(
        "template:default/dns-zone",
        {
            "delegatedZone": PARENT_PRD,
            "prefix": "privatecross",
            "environment": "dev",
            "private": True,
            "vpcs": [DEV_VPC_REF, PRD_VPC_REF],
            "deletionProtection": False,
        },
        "privatecross.arthurbryan.com (env=dev, private, both VPCs)",
    )
    if err:
        fail(err); return 1
    failures = 0

    xr_name = "zone-privatecross.arthurbryan.com"
    obj = wait_ready("system-infrastructure-dev", "zone.dock.tech", xr_name)
    if not obj:
        fail("zone XR absent or not Ready"); return 1
    spec = obj["spec"]
    print(f"  spec.vpcs: {spec.get('vpcs')}")
    print(f"  spec.aws: {spec.get('aws')}")
    print(f"  spec.delegatedFromAccountName: {spec.get('delegatedFromAccountName')}")

    auth = find_mr("system-infrastructure-dev", "vpcassociationauthorization.route53.aws.m.upbound.io",
                   lambda it: it.get("spec", {}).get("forProvider", {}).get("vpcId") == PRD_VPC_ID
                              and it.get("spec", {}).get("forProvider", {}).get("zoneId") == obj.get("status", {}).get("zoneId"))
    if not auth:
        fail("VPCAssociationAuthorization MR not found"); failures += 1
    else:
        pc = auth["spec"]["providerConfigRef"]["name"]
        conds = {c["type"]: c["status"] for c in auth.get("status", {}).get("conditions") or []}
        print(f"  Authorization MR pcRef={pc} ready={conds.get('Ready')} synced={conds.get('Synced')}")
        if pc != "dev-account":
            fail("Authorization MR not using dev-account (zone owner)"); failures += 1
        if conds.get("Ready") != "True" or conds.get("Synced") != "True":
            fail("Authorization MR not Ready/Synced"); failures += 1
        else:
            ok("VPCAssociationAuthorization Ready (zone owner = dev-account)")

    assoc = find_mr("system-infrastructure-dev", "zoneassociation.route53.aws.m.upbound.io",
                    lambda it: it.get("spec", {}).get("forProvider", {}).get("vpcId") == PRD_VPC_ID
                               and it.get("spec", {}).get("forProvider", {}).get("zoneId") == obj.get("status", {}).get("zoneId"))
    if not assoc:
        fail("ZoneAssociation MR not found"); failures += 1
    else:
        pc = assoc["spec"]["providerConfigRef"]["name"]
        conds = {c["type"]: c["status"] for c in assoc.get("status", {}).get("conditions") or []}
        print(f"  ZoneAssociation MR pcRef={pc} ready={conds.get('Ready')} synced={conds.get('Synced')}")
        if pc != "prd-account":
            fail("ZoneAssociation MR not using prd-account (VPC owner)"); failures += 1
        if conds.get("Ready") != "True" or conds.get("Synced") != "True":
            fail("ZoneAssociation MR not Ready/Synced"); failures += 1
        else:
            ok("ZoneAssociation Ready (VPC owner = prd-account)")

    dev_env = aws_env_dev()
    zone_id = obj.get("status", {}).get("zoneId", "")
    elapsed = 0
    vpcs = []
    while elapsed < 180:
        zone_info = aws(["route53", "get-hosted-zone", "--id", zone_id], env=dev_env)
        if zone_info.returncode == 0:
            vpcs = sorted(v["VPCId"] for v in json.loads(zone_info.stdout).get("VPCs", []))
            if DEV_VPC_ID in vpcs and PRD_VPC_ID in vpcs:
                break
        time.sleep(10); elapsed += 10
    print(f"  AWS hosted zone reports VPCs: {vpcs}")
    if DEV_VPC_ID in vpcs and PRD_VPC_ID in vpcs:
        ok("both VPCs associated to the dev-account zone (cross-account works)")
    else:
        fail(f"missing VPCs in zone associations: dev={DEV_VPC_ID in vpcs} prd={PRD_VPC_ID in vpcs}")
        failures += 1
    return failures

def main():
    failures = 0
    failures += test_a_parent_in_dev()
    failures += test_b_record_against_dev_zone()
    failures += test_c_cross_account_private_zone()
    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
