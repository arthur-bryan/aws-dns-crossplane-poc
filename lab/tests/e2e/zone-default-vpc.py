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

PARENT_PRD = "resource:system-infrastructure-prd/zone-arthurbryan.com"
DEV_DEFAULT_VPC = "vpc-0dd3eaef2e5c11f69"
PRD_APP_VPC = "vpc-06c7bbc319e75e472"
PRD_APP_VPC_REF = "resource:default/vpc-06c7bbc319e75e472"
DEV_ACCOUNT = "309670275661"
PRD_ACCOUNT = "597230762851"
DEV_ASSUME_ROLE = f"arn:aws:iam::{DEV_ACCOUNT}:role/OrganizationAccountAccessRole"

PREFIX = "defaultauto"
CHILD_ZONE = f"{PREFIX}.arthurbryan.com"
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


def run(cmd, check=True, env=None):
    return subprocess.run(cmd, check=check, capture_output=True, text=True, env=env)


def aws_env_dev():
    out = run(["kubectl", "-n", "crossplane-system", "get", "secret", "aws-creds",
               "-o", "jsonpath={.data.credentials}"]).stdout
    creds = base64.b64decode(out).decode()
    key = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_access_key_id"))
    secret = next(l.split("=", 1)[1].strip() for l in creds.splitlines() if l.strip().startswith("aws_secret_access_key"))
    base = {**os.environ, "AWS_ACCESS_KEY_ID": key, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "us-east-1"}
    r = run(["aws", "sts", "assume-role", "--role-arn", DEV_ASSUME_ROLE,
             "--role-session-name", "default-vpc-test", "--output", "json"], env=base)
    creds = json.loads(r.stdout)["Credentials"]
    return {**base, "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_TOKEN": creds["SessionToken"]}


def submit_form(values):
    body = {"templateRef": "template:default/dns-zone", "values": values}
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


def merge_and_sync(pr_url):
    pr_num = pr_url.rstrip("/").split("/")[-1]
    subprocess.run(["gh", "pr", "merge", pr_num, "--merge", "--delete-branch"], check=True)
    run(["git", "-C", REPO_ROOT, "fetch", "--quiet", "origin"])
    run(["git", "-C", REPO_ROOT, "pull", "--ff-only", "--quiet"])
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


def wait_zone_ready(name, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        r = run(["kubectl", "-n", CHILD_NAMESPACE, "get", f"zone.dock.tech/{name}", "-o", "json"], check=False)
        if r.returncode == 0:
            obj = json.loads(r.stdout)
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Ready") == "True" and conds.get("Synced") == "True":
                return obj
        time.sleep(5); elapsed += 5
    return None


def main():
    failures = 0
    print(f">>> creating private zone {CHILD_ZONE} (env=dev, user picks ONLY prd-app-vpc)")
    print("    expecting platform to auto-include the dev default VPC plus the picked one")
    task_id = submit_form({
        "delegatedZone": PARENT_PRD,
        "prefix": PREFIX,
        "environment": "dev",
        "private": True,
        "vpcs": [PRD_APP_VPC_REF],
        "deletionProtection": False,
    })
    print(f"  task: {task_id}")
    status = wait_task(task_id)
    print(f"  task status: {status}")
    if status != "completed":
        print("  FAIL submission failed")
        return 1
    pr = task_pr_url(task_id)
    print(f"  PR: {pr}")
    head = merge_and_sync(pr)
    print(f"  HEAD: {head[:12]}, argo synced")

    obj = wait_zone_ready(CHILD_XR)
    if not obj:
        print("  FAIL Zone XR absent / not Ready")
        return 1

    spec_vpcs = obj.get("spec", {}).get("vpcs", [])
    print(f"\n>>> XR spec.vpcs ({len(spec_vpcs)} entries):")
    for v in spec_vpcs:
        print(f"  - {v}")

    has_default = any(v.get("vpcId") == DEV_DEFAULT_VPC and v.get("accountName") == "dev-account" for v in spec_vpcs)
    has_picked = any(v.get("vpcId") == PRD_APP_VPC and v.get("accountName") == "prd-account" for v in spec_vpcs)
    if has_default and has_picked:
        print("  PASS XR has default-dev-vpc + prd-app-vpc")
    else:
        print(f"  FAIL has_default={has_default} has_picked={has_picked}")
        failures += 1

    print(f"\n>>> verify Route53 zone in dev account has both VPCs associated")
    dev_env = aws_env_dev()
    zone_id = obj["status"]["zoneId"]
    elapsed = 0
    aws_vpcs = []
    while elapsed < 180:
        r = run(["aws", "route53", "get-hosted-zone", "--id", zone_id, "--output", "json"], env=dev_env, check=False)
        if r.returncode == 0:
            aws_vpcs = sorted(v["VPCId"] for v in json.loads(r.stdout).get("VPCs", []))
            if DEV_DEFAULT_VPC in aws_vpcs and PRD_APP_VPC in aws_vpcs:
                break
        time.sleep(10); elapsed += 10
    print(f"  AWS reports VPCs: {aws_vpcs}")
    if DEV_DEFAULT_VPC in aws_vpcs and PRD_APP_VPC in aws_vpcs:
        print("  PASS both default-dev-vpc and prd-app-vpc associated in AWS")
    else:
        print(f"  FAIL missing: default={DEV_DEFAULT_VPC in aws_vpcs} app={PRD_APP_VPC in aws_vpcs}")
        failures += 1

    print(f"\n>>> verify the inline same-account VPC is the default (zone XR was bootstrap-able)")
    mr = run(["kubectl", "-n", CHILD_NAMESPACE, "get", f"zone.route53.aws.m.upbound.io/{CHILD_XR}", "-o", "json"], check=False)
    if mr.returncode == 0:
        mrobj = json.loads(mr.stdout)
        inline_vpcs = mrobj.get("spec", {}).get("forProvider", {}).get("vpc", [])
        print(f"  Zone MR spec.forProvider.vpc: {inline_vpcs}")
        inline_ids = [v.get("vpcId") for v in inline_vpcs]
        if DEV_DEFAULT_VPC in inline_ids:
            print("  PASS dev default VPC inlined on the Zone MR")
        else:
            print(f"  FAIL default not inlined: {inline_ids}")
            failures += 1

    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
