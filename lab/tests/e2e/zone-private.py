#!/usr/bin/env python3
"""End-to-end test: create one private zone via the redesigned scaffolder form."""
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

PARENT_ENTITY_REF = "resource:system-infrastructure-dev/zone-arthurbryan.com"
VPC_ENTITY_REF = "resource:default/vpc-0410f81cfe1bba322"
PREFIX = "internal"
PARENT_ZONE = "arthurbryan.com"
CHILD_ZONE = f"{PREFIX}.{PARENT_ZONE}"
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


def run(cmd, check=True, capture=True):
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def step(msg):
    print(f"\n>>> {msg}")


def ok(msg):
    print(f"  PASS  {msg}")


def fail(msg):
    print(f"  FAIL  {msg}")


def submit_form():
    step("submit scaffolder form for internal.arthurbryan.com (private)")
    values = {
        "delegatedZone": PARENT_ENTITY_REF,
        "prefix": PREFIX,
        "private": True,
        "vpcs": [VPC_ENTITY_REF],
        "deletionProtection": False,
    }
    body = {"templateRef": "template:default/aws-dns-zone", "values": values}
    resp = http_json(
        f"{BACKSTAGE}/api/scaffolder/v2/tasks",
        method="POST",
        body=body,
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
        status = info.get("status")
        if status in ("completed", "failed", "cancelled"):
            return status
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


def get_zone_xr(name):
    r = run(["kubectl", "-n", NAMESPACE, "get", f"zone.dock.tech/{name}", "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def wait_zone_ready(name, deadline=300):
    elapsed = 0
    while elapsed < deadline:
        obj = get_zone_xr(name)
        if obj:
            conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
            if conds.get("Synced") == "True" and conds.get("Ready") == "True":
                return obj
        time.sleep(5)
        elapsed += 5
    return get_zone_xr(name)


def find_delegation_mr(parent_zone_name, child_zone_name):
    r = run(["kubectl", "-n", NAMESPACE, "get", "record.route53.aws.m.upbound.io",
             "-o", "json"], check=False)
    if r.returncode != 0:
        return None
    items = json.loads(r.stdout).get("items", [])
    for it in items:
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


def list_zone_picker_entities():
    items = http_json(
        f"{BACKSTAGE}/api/catalog/entities/by-query?filter=spec.type=aws-dns-zone",
        headers={"Authorization": f"Bearer {token()}"},
    )
    return [
        f"{e['kind']}:{e['metadata'].get('namespace','default')}/{e['metadata']['name']}"
        for e in (items.get("items") or [])
    ]


def main():
    failures = 0

    task_id = submit_form()
    print(f"  task: {task_id}")
    status = wait_task(task_id)
    print(f"  task status: {status}")
    for line in task_log_tail(task_id, 30):
        print(line)
    if status != "completed":
        fail("scaffolder task did not complete")
        return 1
    ok("scaffolder task completed")

    pr_url = task_pr_url(task_id)
    if not pr_url:
        fail("no PR URL in task output")
        return 1
    print(f"  PR: {pr_url}")
    ok("PR opened")

    step("merge PR")
    merge_pr(pr_url)
    ok("PR merged")

    step("pull and wait for ArgoCD sync")
    head = git_pull_head()
    print(f"  HEAD: {head[:12]}")
    for app in ARGO_APPS:
        if not argo_wait(app, head):
            fail(f"argo app {app} did not sync to {head[:12]}")
            failures += 1
        else:
            ok(f"argo app {app} synced")

    step(f"verify Zone XR {CHILD_XR} ready")
    obj = wait_zone_ready(CHILD_XR)
    if not obj:
        fail("Zone XR absent")
        return 1
    conds = {c["type"]: c["status"] for c in obj.get("status", {}).get("conditions") or []}
    print(f"  conditions: {conds}")
    print(f"  zoneId: {obj.get('status', {}).get('zoneId')}")
    print(f"  nameServers: {obj.get('status', {}).get('nameServers')}")
    print(f"  delegatedFromZoneId (spec): {obj.get('spec', {}).get('delegatedFromZoneId')}")
    print(f"  visibility (spec): {obj.get('spec', {}).get('visibility')}")
    print(f"  vpcs (spec): {obj.get('spec', {}).get('vpcs')}")
    if conds.get("Ready") != "True":
        fail("Zone XR not Ready")
        failures += 1
    else:
        ok("Zone XR Ready")

    step(f"verify NS delegation record in parent zone")
    elapsed = 0
    deleg = None
    while elapsed < 180 and deleg is None:
        deleg = find_delegation_mr(PARENT_ZONE, CHILD_ZONE)
        if deleg is None:
            time.sleep(5)
            elapsed += 5
    if not deleg:
        fail(f"NS delegation Record MR for {CHILD_ZONE} not found")
        failures += 1
    else:
        spec = deleg["spec"]["forProvider"]
        print(f"  delegation MR: {deleg['metadata']['name']}")
        print(f"    name: {spec.get('name')}  type: {spec.get('type')}  zoneId: {spec.get('zoneId')}")
        print(f"    records: {spec.get('records')}")
        conds = {c["type"]: c["status"] for c in deleg.get("status", {}).get("conditions") or []}
        print(f"    conditions: {conds}")
        if conds.get("Ready") != "True":
            fail("delegation NS record not Ready")
            failures += 1
        else:
            ok("delegation NS record Ready")

    step("verify new zone catalog entity")
    new_entity_ref = f"resource:{NAMESPACE}/{CHILD_XR}"
    if wait_catalog(new_entity_ref):
        ok(f"catalog has {new_entity_ref}")
    else:
        fail(f"catalog missing {new_entity_ref}")
        failures += 1

    step("verify new zone visible in record-creation EntityPicker")
    picker = list_zone_picker_entities()
    print(f"  zones in picker: {picker}")
    if any(CHILD_XR in r for r in picker):
        ok(f"{CHILD_XR} visible to record EntityPicker (filter spec.type=aws-dns-zone)")
    else:
        fail(f"{CHILD_XR} not in record EntityPicker results")
        failures += 1

    print()
    print("=" * 60)
    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
