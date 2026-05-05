#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
NAMESPACE = "system-infrastructure-dev"
BACKSTAGE = os.environ.get("BACKSTAGE_BACKEND", "http://localhost:7007")
ARGO_APPS = ["entities", "lab-root", "crossplane-compositions-dns"]

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

def run(cmd, check=True, capture=True):
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)

def step(msg):
    print(f"\n>>> {msg}")

def ok(msg):
    print(f"  PASS  {msg}")

def fail(msg):
    print(f"  FAIL  {msg}")

def submit(template_ref, values):
    body = {"templateRef": template_ref, "values": values}
    resp = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks",
        method="POST", body=body,
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

def task_log_tail(task_id, n=20):
    events = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
        headers={"Authorization": f"Bearer {token()}"},
    ) or []
    msgs = []
    for ev in events:
        body = ev.get("body") or {}
        msg = body.get("message")
        if msg:
            msgs.append(f"  [{ev.get('type')}] {body.get('stepId') or '-'}: {msg.strip().splitlines()[0][:160]}")
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

def get_xr(kind_resource, name):
    r = run(["kubectl", "-n", NAMESPACE, "get", f"{kind_resource}/{name}", "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)

def wait_ready(kind_resource, name, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        obj = get_xr(kind_resource, name)
        if obj:
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Synced") == "True" and conds.get("Ready") == "True":
                return obj
        time.sleep(5)
        elapsed += 5
    return get_xr(kind_resource, name)

def find_delegation_mr(child_zone_name):
    r = run(["kubectl", "-n", NAMESPACE, "get", "record.route53.aws.m.upbound.io",
             "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    for it in json.loads(r.stdout).get("items", []):
        spec = it.get("spec", {}).get("forProvider", {})
        if spec.get("type") == "NS" and spec.get("name") == child_zone_name:
            return it
    return None

def wait_catalog(entity_ref, deadline=120):
    kind, rest = entity_ref.split(":", 1)
    namespace, name = rest.split("/", 1)
    elapsed = 0
    while elapsed < deadline:
        try:
            http_json(
                f"{BACKSTAGE}/api/catalog/entities/by-name/{kind}/{namespace}/{name}",
                headers={"Authorization": f"Bearer {token()}"},
            )
            return True
        except Exception:
            pass
        time.sleep(3)
        elapsed += 3
    return False

def submit_pr_merge_sync(template_ref, values):
    task_id = submit(template_ref, values)
    print(f"  task: {task_id}")
    status = wait_task(task_id)
    print(f"  task status: {status}")
    for line in task_log_tail(task_id, 25):
        print(line)
    if status != "completed":
        return None, "task not completed"
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

def test_record_against_internal():
    step("create A record test.internal.arthurbryan.com -> 10.0.0.42 via the form")
    head, err = submit_pr_merge_sync(
        "template:default/aws-dns-record",
        {
            "zone": "resource:system-infrastructure-dev/zone-internal.arthurbryan.com",
            "recordName": "test",
            "type": "A",
            "ttl": 300,
            "values": ["10.0.0.42"],
            "routingPolicy": "simple",
        },
    )
    if err:
        fail(err); return 1
    ok("PR merged + ArgoCD synced")

    xr_name = "record-test.internal.arthurbryan.com"
    obj = wait_ready("record.dock.tech", xr_name)
    if not obj:
        fail(f"Record XR {xr_name} absent"); return 1
    spec = obj.get("spec", {})
    conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
    print(f"  zoneId in XR spec: {spec.get('zoneId')}")
    print(f"  conditions: {conds}")
    if spec.get("zoneId") != "Z023605847CN76CUAJYF":
        fail(f"Record XR has wrong zoneId {spec.get('zoneId')}"); return 1
    if conds.get("Ready") != "True":
        fail("Record XR not Ready"); return 1
    ok("Record XR Ready and pointed at internal zone's zoneId")

    mr = run(["kubectl", "-n", NAMESPACE, "get", "record.route53.aws.m.upbound.io",
              "-o", "json"], check=False)
    items = json.loads(mr.stdout).get("items", []) if mr.returncode == 0 else []
    target = None
    for it in items:
        s = it.get("spec", {}).get("forProvider", {})
        if s.get("type") == "A" and s.get("name") == "test.internal.arthurbryan.com":
            target = it
            break
    if not target:
        fail("Route53 Record MR for test.internal.arthurbryan.com not found"); return 1
    print(f"  MR records: {target['spec']['forProvider'].get('records')}")
    print(f"  MR zoneId: {target['spec']['forProvider'].get('zoneId')}")
    if target['spec']['forProvider'].get('zoneId') != "Z023605847CN76CUAJYF":
        fail("MR zoneId mismatch"); return 1
    ok("Route53 Record MR materialized in the right hosted zone")
    return 0

def test_public_zone():
    step("create public zone external.arthurbryan.com via the form")
    head, err = submit_pr_merge_sync(
        "template:default/aws-dns-zone",
        {
            "delegatedZone": "resource:system-infrastructure-dev/zone-arthurbryan.com",
            "prefix": "external",
            "private": False,
            "deletionProtection": False,
        },
    )
    if err:
        fail(err); return 1
    ok("PR merged + ArgoCD synced")

    xr_name = "zone-external.arthurbryan.com"
    obj = wait_ready("zone.dock.tech", xr_name)
    if not obj:
        fail(f"Zone XR {xr_name} absent"); return 1
    spec = obj.get("spec", {})
    status = obj.get("status", {})
    conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
    print(f"  zoneId: {status.get('zoneId')}")
    print(f"  visibility (spec): {spec.get('visibility')}")
    print(f"  vpcs (spec): {spec.get('vpcs')}")
    print(f"  delegatedFromZoneId (spec): {spec.get('delegatedFromZoneId')}")
    print(f"  conditions: {conds}")
    if spec.get("visibility") != "public" or spec.get("vpcs"):
        fail("public zone has unexpected vpcs / visibility"); return 1
    if conds.get("Ready") != "True":
        fail("Zone XR not Ready"); return 1
    ok("Zone XR Ready (public, no VPCs)")

    deleg = None
    elapsed = 0
    while elapsed < 180 and deleg is None:
        deleg = find_delegation_mr("external.arthurbryan.com")
        if deleg is None:
            time.sleep(5); elapsed += 5
    if not deleg:
        fail("NS delegation MR not found"); return 1
    dconds = {c["type"]: c["status"] for c in deleg.get("status", {}).get("conditions") or []}
    print(f"  delegation MR records: {deleg['spec']['forProvider'].get('records')}")
    print(f"  delegation conditions: {dconds}")
    if dconds.get("Ready") != "True":
        fail("delegation NS not Ready"); return 1
    ok("NS delegation Ready in parent zone")

    if not wait_catalog(f"resource:{NAMESPACE}/{xr_name}"):
        fail(f"catalog missing {xr_name}"); return 1
    ok("catalog has the new zone entity")
    return 0

def main():
    failures = 0
    failures += test_record_against_internal()
    failures += test_public_zone()

    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
