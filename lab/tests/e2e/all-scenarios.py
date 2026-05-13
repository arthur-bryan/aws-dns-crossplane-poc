#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
ZONE_NAME = os.environ.get("E2E_ZONE_NAME", "arthurbryan.com")
ZONE_ID = os.environ.get("E2E_ZONE_ID", "Z03010981ALJFZB4QLU8W")
ZONE_NAMESPACE = os.environ.get("E2E_ZONE_NAMESPACE", "system-infrastructure-prd")
ZONE_ENVIRONMENT = ZONE_NAMESPACE.split("-")[-1]  # "prd" or "dev" (matches dock.tech/environment annotation on the parent zone)
ZONE_REF = f"resource:{ZONE_NAMESPACE}/zone-{ZONE_NAME}"
NAMESPACE = ZONE_NAMESPACE
BACKSTAGE = os.environ.get("BACKSTAGE_BACKEND", "http://localhost:7007")
GH_OWNER = "arthur-bryan"
GH_REPO = "aws-dns-crossplane-poc"
GH_BRANCH = "feature/ape-platform-alignment"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
NC = "\033[0m"

def out(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}{NC}", flush=True)

def step(msg: str) -> None:
    print(f"\n{BOLD}=== {msg} ==={NC}", flush=True)

def info(msg: str) -> None:
    out(YELLOW, f"  [info] {msg}")

def ok(msg: str) -> None:
    out(GREEN, f"  [ok]   {msg}")

def fail(msg: str) -> None:
    out(RED, f"  [fail] {msg}")

def run(cmd: list[str], check: bool = True, capture: bool = True, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=capture, env=env or os.environ)

def aws_env() -> dict[str, str]:
    creds_b64 = run(["kubectl", "-n", "crossplane-system", "get", "secret", "aws-creds",
                     "-o", "jsonpath={.data.credentials}"]).stdout
    creds = subprocess.check_output(["base64", "-d"], input=creds_b64, text=True)
    key = secret = ""
    for line in creds.splitlines():
        if "aws_access_key_id" in line:
            key = line.split("=", 1)[1].strip()
        elif "aws_secret_access_key" in line:
            secret = line.split("=", 1)[1].strip()
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = key
    env["AWS_SECRET_ACCESS_KEY"] = secret
    env.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    return env

def aws(*args: str) -> dict | list:
    result = run(["aws", *args, "--output", "json"], env=aws_env())
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)

def http_json(url: str, *, method: str = "GET", body: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    if not raw:
        return None
    return json.loads(raw)

def backstage_token() -> str:
    return http_json(f"{BACKSTAGE}/api/auth/guest/refresh")["backstageIdentity"]["token"]

def scaffolder_submit(template_ref: str, values: dict) -> str:
    token = backstage_token()
    body = {"templateRef": template_ref, "values": values}
    resp = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks",
                     method="POST", body=body,
                     headers={"Authorization": f"Bearer {token}"})
    return resp["id"]

def scaffolder_task(task_id: str) -> dict:
    token = backstage_token()
    return http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}",
                     headers={"Authorization": f"Bearer {token}"})

def scaffolder_events(task_id: str) -> list[dict]:
    token = backstage_token()
    resp = http_json(f"{BACKSTAGE}/api/scaffolder/v2/tasks/{task_id}/events",
                     headers={"Authorization": f"Bearer {token}"})
    return resp or []

def scaffolder_wait(task_id: str, deadline: int = 240) -> str:
    elapsed = 0
    while elapsed < deadline:
        status = scaffolder_task(task_id).get("status", "")
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(3)
        elapsed += 3
    return "timeout"

def scaffolder_pr_url(task_id: str) -> Optional[str]:
    for ev in scaffolder_events(task_id):
        if ev.get("type") != "completion":
            continue
        output = (ev.get("body") or {}).get("output") or {}
        for link in output.get("links") or []:
            if link.get("url"):
                return link["url"]
    return None

def scaffolder_log_tail(task_id: str, n: int = 12) -> list[str]:
    msgs: list[str] = []
    for ev in scaffolder_events(task_id):
        body = ev.get("body") or {}
        msg = body.get("message")
        if msg:
            msgs.append(f"[{ev.get('type')}] {body.get('stepId') or '-'}: {msg.strip().splitlines()[0][:160]}")
    return msgs[-n:]

def gh_pr_merge(pr_url: str) -> None:
    pr_num = pr_url.rstrip("/").split("/")[-1]
    run(["gh", "pr", "merge", pr_num, "--merge", "--delete-branch"], capture=False)

def gh_pr_close(pr_url: str, comment: str = "") -> None:
    pr_num = pr_url.rstrip("/").split("/")[-1]
    args = ["gh", "pr", "close", pr_num, "--delete-branch"]
    if comment:
        args += ["--comment", comment]
    run(args, capture=False)

def git_pull() -> str:
    run(["git", "-C", REPO_ROOT, "fetch", "--quiet", "origin"])
    run(["git", "-C", REPO_ROOT, "pull", "--ff-only", "--quiet"])
    return run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"]).stdout.strip()

def argo_wait_revision(app: str, revision: str, deadline: int = 240) -> bool:
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

def xr_status(xr_name: str) -> dict:
    cmd = ["kubectl", "-n", NAMESPACE, "get", f"record.dock.tech/{xr_name}", "-o", "json"]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return {"absent": True}
    obj = json.loads(r.stdout)
    conds = {c["type"]: (c["status"], c.get("reason", ""), c.get("message", "")) for c in obj.get("status", {}).get("conditions") or []}
    return {
        "absent": False,
        "type": obj["spec"].get("type"),
        "ttl": obj["spec"].get("ttl"),
        "values": obj["spec"].get("values", []),
        "set_identifier": obj["spec"].get("setIdentifier"),
        "weight": obj["spec"].get("weight"),
        "deletion_timestamp": obj["metadata"].get("deletionTimestamp"),
        "synced": conds.get("Synced", ("", "", ""))[0],
        "ready": conds.get("Ready", ("", "", ""))[0],
        "synced_msg": conds.get("Synced", ("", "", ""))[2],
    }

def mr_status(mr_name: str) -> dict:
    cmd = ["kubectl", "-n", NAMESPACE, "get", f"record.route53.aws.m.upbound.io/{mr_name}", "-o", "json"]
    r = run(cmd, check=False)
    if r.returncode != 0:
        return {"absent": True}
    obj = json.loads(r.stdout)
    conds = {c["type"]: (c["status"], c.get("reason", ""), c.get("message", "")) for c in obj.get("status", {}).get("conditions") or []}
    return {
        "absent": False,
        "synced": conds.get("Synced", ("", "", ""))[0],
        "ready": conds.get("Ready", ("", "", ""))[0],
        "synced_msg": conds.get("Synced", ("", "", ""))[2],
        "external_name": obj["metadata"].get("annotations", {}).get("crossplane.io/external-name"),
    }

def wait_xr_ready(xr_name: str, deadline: int = 240) -> bool:
    elapsed = 0
    while elapsed < deadline:
        s = xr_status(xr_name)
        if not s.get("absent") and s.get("synced") == "True" and s.get("ready") == "True":
            return True
        time.sleep(5)
        elapsed += 5
    return False

def wait_catalog_entity(entity_ref: str, deadline: int = 120) -> bool:
    parts = entity_ref.split(":", 1)[1]
    namespace, name = parts.split("/", 1)
    kind = entity_ref.split(":", 1)[0]
    elapsed = 0
    while elapsed < deadline:
        try:
            token = backstage_token()
            http_json(f"{BACKSTAGE}/api/catalog/entities/by-name/{kind}/{namespace}/{name}",
                      headers={"Authorization": f"Bearer {token}"})
            return True
        except Exception:
            pass
        time.sleep(3)
        elapsed += 3
    return False

def wait_catalog_entity_absent(entity_ref: str, deadline: int = 120) -> bool:
    parts = entity_ref.split(":", 1)[1]
    namespace, name = parts.split("/", 1)
    kind = entity_ref.split(":", 1)[0]
    elapsed = 0
    while elapsed < deadline:
        try:
            token = backstage_token()
            http_json(f"{BACKSTAGE}/api/catalog/entities/by-name/{kind}/{namespace}/{name}",
                      headers={"Authorization": f"Bearer {token}"})
        except Exception:
            return True
        time.sleep(3)
        elapsed += 3
    return False

def aws_records_at(fqdn: str) -> list[dict]:
    res = aws("route53", "list-resource-record-sets",
              "--hosted-zone-id", ZONE_ID,
              "--query", f"ResourceRecordSets[?Name=='{fqdn}.']")
    return res or []

_HEALTH_CHECK_CACHE: dict[str, str] = {}

def ensure_health_check(label: str) -> str:
    if label in _HEALTH_CHECK_CACHE:
        return _HEALTH_CHECK_CACHE[label]
    config = {
        "Type": "HTTP",
        "ResourcePath": "/",
        "FullyQualifiedDomainName": "example.com",
        "Port": 80,
        "RequestInterval": 30,
        "FailureThreshold": 3,
    }
    res = aws("route53", "create-health-check",
              "--caller-reference", f"e2e-{label}-{int(time.time())}",
              "--health-check-config", json.dumps(config))
    hc_id = res["HealthCheck"]["Id"]
    _HEALTH_CHECK_CACHE[label] = hc_id
    return hc_id

def delete_health_check(hc_id: str) -> None:
    try:
        aws("route53", "delete-health-check", "--health-check-id", hc_id)
    except subprocess.CalledProcessError:
        pass

def cleanup_all_health_checks() -> None:
    for hc_id in list(_HEALTH_CHECK_CACHE.values()):
        delete_health_check(hc_id)
    _HEALTH_CHECK_CACHE.clear()

def base_key(record_name: str, rtype: str, set_id: Optional[str]) -> str:
    base = record_name if record_name else f"apex-{rtype.lower()}"
    if set_id:
        base = f"{base}-{set_id}"
    return base.lower()

def xr_path(zone: str, key: str) -> str:
    return f"entities/environments/cross/cloud/infrastructure/{ZONE_ENVIRONMENT}/resources/aws/{zone}/record-{key}.yaml"

def catalog_path(env: str, zone: str, key: str) -> str:
    return f"entities/catalog/{env}/{zone}/record-{key}.yaml"

@dataclass
class Scenario:
    name: str
    record_name: str
    record_type: str
    create_values: dict[str, Any]
    edit_values: dict[str, Any]
    expected_aws: Callable[[list[dict]], tuple[bool, str]]
    expected_aws_after_edit: Callable[[list[dict]], tuple[bool, str]]
    set_identifier: Optional[str] = None
    extra_create: dict[str, Any] = field(default_factory=dict)
    extra_edit: dict[str, Any] = field(default_factory=dict)

def submit_create(scenario: Scenario) -> tuple[Optional[str], Optional[str]]:
    values = {
        "zone": ZONE_REF,
        "recordName": scenario.record_name,
        "type": scenario.record_type,
    }
    values.update(scenario.create_values)
    values.update(scenario.extra_create)
    info(f"submit create {scenario.name}")
    task_id = scaffolder_submit("template:default/aws-dns-record", values)
    state = scaffolder_wait(task_id)
    if state != "completed":
        fail(f"create task {task_id} state={state}")
        for line in scaffolder_log_tail(task_id):
            print(f"        {line}")
        return None, None
    pr = scaffolder_pr_url(task_id)
    if not pr:
        fail(f"no PR url on task {task_id}")
        return None, None
    ok(f"create PR: {pr}")
    return task_id, pr

def submit_edit(scenario: Scenario) -> tuple[Optional[str], Optional[str]]:
    values = {
        "zone": ZONE_REF,
        "recordName": scenario.record_name,
        "type": scenario.record_type,
    }
    if scenario.set_identifier:
        values["setIdentifier"] = scenario.set_identifier
    values.update(scenario.edit_values)
    values.update(scenario.extra_edit)
    info(f"submit edit {scenario.name}")
    task_id = scaffolder_submit("template:default/aws-dns-record-edit", values)
    state = scaffolder_wait(task_id)
    if state != "completed":
        fail(f"edit task {task_id} state={state}")
        for line in scaffolder_log_tail(task_id):
            print(f"        {line}")
        return None, None
    pr = scaffolder_pr_url(task_id)
    if not pr:
        fail(f"no PR url on edit task {task_id}")
        return None, None
    ok(f"edit PR: {pr}")
    return task_id, pr

def merge_pr(pr_url: str) -> bool:
    info(f"auto-merging {pr_url}")
    try:
        gh_pr_merge(pr_url)
    except subprocess.CalledProcessError as exc:
        fail(f"merge failed: {exc}")
        return False
    return True

def post_merge_validate(scenario: Scenario, after_edit: bool = False) -> bool:
    head = git_pull()
    info(f"HEAD = {head}")
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync")
        return False
    ok(f"argo synced {head[:10]}")

    key = base_key(scenario.record_name, scenario.record_type, scenario.set_identifier)
    xr_name = f"record-{key}.{ZONE_NAME}"
    if not wait_xr_ready(xr_name, 240):
        s = xr_status(xr_name)
        m = mr_status(xr_name)
        fail(f"XR not Ready  XR={s}  MR={m}")
        return False
    ok(f"XR {xr_name} Synced+Ready")

    fqdn = f"{scenario.record_name}.{ZONE_NAME}" if scenario.record_name else ZONE_NAME
    rows = aws_records_at(fqdn)
    expected = scenario.expected_aws_after_edit if after_edit else scenario.expected_aws
    okp, msg = expected(rows)
    if not okp:
        fail(f"AWS check: {msg}")
        return False
    ok(f"AWS: {msg}")
    return True

def cleanup_record(scenario: Scenario) -> bool:
    key = base_key(scenario.record_name, scenario.record_type, scenario.set_identifier)
    xr_rel = xr_path(ZONE_NAME, key)
    cat_rel = catalog_path(ZONE_ENVIRONMENT, ZONE_NAME, key)

    if not os.path.exists(os.path.join(REPO_ROOT, xr_rel)):
        info("nothing to cleanup (file already removed)")
        return True

    info(f"removing {xr_rel} + {cat_rel} via PR")
    branch = f"e2e-cleanup-{key}-{int(time.time())}"
    run(["git", "-C", REPO_ROOT, "checkout", "-b", branch])
    run(["git", "-C", REPO_ROOT, "rm", xr_rel, cat_rel])
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Arthur Bryan"
    env["GIT_AUTHOR_EMAIL"] = "arthurbryan2030@gmail.com"
    env["GIT_COMMITTER_NAME"] = "Arthur Bryan"
    env["GIT_COMMITTER_EMAIL"] = "arthurbryan2030@gmail.com"
    run(["git", "-c", "user.name=Arthur Bryan", "-c", "user.email=arthurbryan2030@gmail.com",
         "-C", REPO_ROOT, "commit", "-m", f"chore(e2e): remove test record {scenario.name}"], env=env)
    run(["git", "-C", REPO_ROOT, "push", "-u", "origin", branch])
    pr_create = run(["gh", "pr", "create", "--base", GH_BRANCH, "--head", branch,
                     "--title", f"chore(e2e): remove test record {scenario.name}",
                     "--body", "automated e2e cleanup"])
    pr_url = pr_create.stdout.strip().splitlines()[-1]
    ok(f"cleanup PR: {pr_url}")
    if not merge_pr(pr_url):
        return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync cleanup commit")
        return False
    fqdn = f"{scenario.record_name}.{ZONE_NAME}" if scenario.record_name else ZONE_NAME
    elapsed = 0
    while elapsed < 180:
        rows = aws_records_at(fqdn)
        rows_for_set = [r for r in rows if (r.get("SetIdentifier") or None) == scenario.set_identifier]
        if not rows_for_set or all(r.get("Type") != scenario.record_type for r in rows_for_set):
            ok("AWS row gone")
            return True
        time.sleep(5)
        elapsed += 5
    fail("AWS row still present after 180s")
    return False

def run_scenario(scenario: Scenario, *, do_edit: bool = True, do_cleanup: bool = True) -> bool:
    step(f"SCENARIO {scenario.name} ({scenario.record_type})")
    _, pr = submit_create(scenario)
    if not pr:
        return False
    if not merge_pr(pr):
        return False
    if not post_merge_validate(scenario):
        return False

    if do_edit:
        key = base_key(scenario.record_name, scenario.record_type, scenario.set_identifier)
        entity_ref = f"resource:{NAMESPACE}/record-{key}.{ZONE_NAME}"
        if not wait_catalog_entity(entity_ref, 120):
            fail(f"catalog did not pick up {entity_ref}")
            return False
        ok(f"catalog has {entity_ref}")
        _, pr = submit_edit(scenario)
        if not pr:
            return False
        if not merge_pr(pr):
            return False
        if not post_merge_validate(scenario, after_edit=True):
            return False

    if do_cleanup:
        if not cleanup_record(scenario):
            return False
    return True

def values_match(rows: list[dict], rtype: str, expected_values: list[str], expected_ttl: int,
                 set_identifier: Optional[str] = None,
                 weight: Optional[int] = None) -> tuple[bool, str]:
    target = [r for r in rows if r.get("Type") == rtype]
    if set_identifier is not None:
        target = [r for r in target if r.get("SetIdentifier") == set_identifier]
    if not target:
        return False, f"no row matching type={rtype} setId={set_identifier}"
    row = target[0]
    if row.get("TTL") != expected_ttl:
        return False, f"TTL {row.get('TTL')} != {expected_ttl}"
    got_vals = sorted([rr.get("Value") for rr in row.get("ResourceRecords") or []])
    want_vals = sorted(expected_values)
    if got_vals != want_vals:
        return False, f"values {got_vals} != {want_vals}"
    if weight is not None and row.get("Weight") != weight:
        return False, f"weight {row.get('Weight')} != {weight}"
    pieces = [f"type={rtype}", f"ttl={expected_ttl}", f"values={got_vals}"]
    if set_identifier:
        pieces.append(f"setId={set_identifier}")
    if weight is not None:
        pieces.append(f"weight={weight}")
    return True, " ".join(pieces)

def alias_match(rows: list[dict], expected_dns: str, expected_zone_id: str,
                set_identifier: Optional[str] = None) -> tuple[bool, str]:
    target = [r for r in rows if r.get("Type") in ("A", "AAAA") and r.get("AliasTarget")]
    if set_identifier is not None:
        target = [r for r in target if r.get("SetIdentifier") == set_identifier]
    if not target:
        return False, "no alias row"
    al = target[0]["AliasTarget"]
    got_dns = (al.get("DNSName") or "").rstrip(".")
    want_dns = expected_dns.rstrip(".")
    if got_dns != want_dns:
        return False, f"alias dnsName {got_dns} != {want_dns}"
    if al.get("HostedZoneId") != expected_zone_id:
        return False, f"alias zoneId {al.get('HostedZoneId')} != {expected_zone_id}"
    return True, f"alias dnsName={got_dns} zoneId={al.get('HostedZoneId')}"

def make_a(suffix: str) -> Scenario:
    name = f"a-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["192.0.2.50"]
    edit_v = ["192.0.2.51", "192.0.2.52"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "A", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", edit_v, 600),
    )

def make_aaaa(suffix: str) -> Scenario:
    name = f"aaaa-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["2001:db8::100"]
    edit_v = ["2001:db8::101"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="AAAA",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "AAAA", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "AAAA", edit_v, 600),
    )

def make_cname(suffix: str) -> Scenario:
    name = f"cname-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["e2e-target.example.com"]
    edit_v = ["e2e-target-2.example.com"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="CNAME",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "CNAME", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "CNAME", edit_v, 600),
    )

def make_txt(suffix: str) -> Scenario:
    name = f"txt-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ['"hello-e2e"']
    edit_v = ['"hello-e2e-edited"']
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="TXT",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "TXT", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "TXT", edit_v, 600),
    )

def make_mx(suffix: str) -> Scenario:
    name = f"mx-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["10 mail1.example.com"]
    edit_v = ["10 mail1.example.com", "20 mail2.example.com"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="MX",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "MX", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "MX", edit_v, 600),
    )

def make_ptr(suffix: str) -> Scenario:
    name = f"ptr-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["host1.example.com"]
    edit_v = ["host2.example.com"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="PTR",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "PTR", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "PTR", edit_v, 600),
    )

def make_srv(suffix: str) -> Scenario:
    name = f"srv-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["10 60 5060 sip1.example.com"]
    edit_v = ["10 60 5060 sip1.example.com", "20 60 5060 sip2.example.com"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="SRV",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "SRV", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "SRV", edit_v, 600),
    )

def make_caa(suffix: str) -> Scenario:
    name = f"caa-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ['0 issue "letsencrypt.org"']
    edit_v = ['0 issue "letsencrypt.org"', '0 issue "amazon.com"']
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="CAA",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "CAA", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "CAA", edit_v, 600),
    )

def make_ns_subdelegation(suffix: str) -> Scenario:
    name = f"ns-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["ns1.example.com", "ns2.example.com"]
    edit_v = ["ns1.example.com", "ns2.example.com", "ns3.example.com"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="NS",
        create_values={"ttl": 172800, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 86400, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "NS", create_v, 172800),
        expected_aws_after_edit=lambda rows: values_match(rows, "NS", edit_v, 86400),
    )

def make_alias_custom(suffix: str) -> Scenario:
    name = f"alias-custom-{suffix}"
    record_name = f"e2e-{name}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="ALIAS",
        create_values={
            "routingPolicy": "simple",
            "serviceType": "Custom",
            "dnsName": "d111-create.cloudfront.net",
            "evaluateTargetHealth": False,
            "customZoneId": "Z2FDTNDATAQYW2",
        },
        edit_values={
            "serviceType": "Custom",
            "dnsName": "d222-edit.cloudfront.net",
            "evaluateTargetHealth": False,
        },
        expected_aws=lambda rows: alias_match(rows, "d111-create.cloudfront.net", "Z2FDTNDATAQYW2"),
        expected_aws_after_edit=lambda rows: alias_match(rows, "d222-edit.cloudfront.net", "Z2FDTNDATAQYW2"),
    )

def make_weighted(suffix: str, set_id: str, weight_create: int, weight_edit: int,
                  values_create: list[str], values_edit: list[str]) -> Scenario:
    name = f"weighted-{suffix}-{set_id}"
    record_name = f"e2e-weighted-{suffix}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "weighted",
            "setIdentifier": set_id,
            "weight": weight_create,
            "ttl": 300,
            "values": values_create,
        },
        edit_values={"ttl": 600, "values": values_edit, "weight": weight_edit},
        expected_aws=lambda rows: values_match(rows, "A", values_create, 300, set_identifier=set_id, weight=weight_create),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", values_edit, 600, set_identifier=set_id, weight=weight_edit),
    )

def make_failover(suffix: str, set_id: str, role: str, value: str, edit_value: str) -> Scenario:
    name = f"failover-{suffix}-{set_id}"
    record_name = f"e2e-failover-{suffix}"
    create = {
        "routingPolicy": "failover",
        "setIdentifier": set_id,
        "failoverType": role,
        "ttl": 300,
        "values": [value],
    }
    if role == "PRIMARY":
        create["healthCheckId"] = ensure_health_check(f"failover-{suffix}")
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values=create,
        edit_values={"ttl": 600, "values": [edit_value]},
        expected_aws=lambda rows: values_match(rows, "A", [value], 300, set_identifier=set_id),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", [edit_value], 600, set_identifier=set_id),
    )

def make_latency(suffix: str, set_id: str, region: str, value: str, edit_value: str) -> Scenario:
    name = f"latency-{suffix}-{set_id}"
    record_name = f"e2e-latency-{suffix}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "latency",
            "setIdentifier": set_id,
            "latencyRegion": region,
            "ttl": 300,
            "values": [value],
        },
        edit_values={"ttl": 600, "values": [edit_value]},
        expected_aws=lambda rows: values_match(rows, "A", [value], 300, set_identifier=set_id),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", [edit_value], 600, set_identifier=set_id),
    )

def make_geolocation(suffix: str, set_id: str, continent: str, value: str, edit_value: str) -> Scenario:
    name = f"geo-{suffix}-{set_id}"
    record_name = f"e2e-geo-{suffix}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "geolocation",
            "setIdentifier": set_id,
            "geoContinent": continent,
            "ttl": 300,
            "values": [value],
        },
        edit_values={"ttl": 600, "values": [edit_value]},
        expected_aws=lambda rows: values_match(rows, "A", [value], 300, set_identifier=set_id),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", [edit_value], 600, set_identifier=set_id),
    )

def make_geoproximity(suffix: str, set_id: str, region: str, value: str, edit_value: str) -> Scenario:
    name = f"geoprox-{suffix}-{set_id}"
    record_name = f"e2e-geoprox-{suffix}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "geoproximity",
            "setIdentifier": set_id,
            "geoproxAwsRegion": region,
            "geoproxBias": 0,
            "ttl": 300,
            "values": [value],
        },
        edit_values={"ttl": 600, "values": [edit_value]},
        expected_aws=lambda rows: values_match(rows, "A", [value], 300, set_identifier=set_id),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", [edit_value], 600, set_identifier=set_id),
    )

def make_multivalue(suffix: str, set_id: str, value: str, edit_value: str) -> Scenario:
    name = f"multi-{suffix}-{set_id}"
    record_name = f"e2e-multi-{suffix}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "multivalue",
            "setIdentifier": set_id,
            "ttl": 300,
            "values": [value],
        },
        edit_values={"ttl": 600, "values": [edit_value]},
        expected_aws=lambda rows: values_match(rows, "A", [value], 300, set_identifier=set_id),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", [edit_value], 600, set_identifier=set_id),
    )

# ---------------------------------------------------------------------------
# Single-axis edits: prove that ChangeResourceRecordSets UPSERT mutates only
# the field that changed.
# ---------------------------------------------------------------------------

def make_a_ttl_only(suffix: str) -> Scenario:
    name = f"a-ttl-only-{suffix}"
    record_name = f"e2e-{name}"
    values = ["192.0.2.80"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        create_values={"ttl": 300, "values": values, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": values},  # values unchanged on purpose
        expected_aws=lambda rows: values_match(rows, "A", values, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", values, 600),
    )

def make_a_values_only(suffix: str) -> Scenario:
    name = f"a-values-only-{suffix}"
    record_name = f"e2e-{name}"
    create_v = ["192.0.2.90"]
    edit_v = ["192.0.2.91"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 300, "values": edit_v},  # ttl unchanged on purpose
        expected_aws=lambda rows: values_match(rows, "A", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", edit_v, 300),
    )

def make_weighted_weight_only(suffix: str) -> Scenario:
    # set_id stays short — total length of metadata.name on the resulting
    # Record MR (record-<recordName>-<setId>.<zoneName>) must fit in 63 bytes
    set_id = "wo"
    name = f"weighted-weight-only-{suffix}"
    record_name = f"e2e-{name}"
    values = ["10.0.11.50"]
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="A",
        set_identifier=set_id,
        create_values={
            "routingPolicy": "weighted",
            "setIdentifier": set_id,
            "weight": 10,
            "ttl": 300,
            "values": values,
        },
        edit_values={"weight": 100, "ttl": 300, "values": values},
        expected_aws=lambda rows: values_match(rows, "A", values, 300, set_identifier=set_id, weight=10),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", values, 300, set_identifier=set_id, weight=100),
    )

# ---------------------------------------------------------------------------
# Apex variants (recordName="") exercise the `if $recordName` branch in the
# composition's external-name builder.
# ---------------------------------------------------------------------------

def make_a_apex(suffix: str) -> Scenario:
    name = f"a-apex-{suffix}"
    create_v = ["192.0.2.200"]
    edit_v = ["192.0.2.201"]
    # An apex A on the same zone would clash with the real apex record. This
    # scenario only runs on a dedicated test zone — set ALLOW_APEX_TEST=1 to
    # opt in, otherwise the runner skips it.
    return Scenario(
        name=name,
        record_name="",  # apex
        record_type="A",
        create_values={"ttl": 300, "values": create_v, "routingPolicy": "simple"},
        edit_values={"ttl": 600, "values": edit_v},
        expected_aws=lambda rows: values_match(rows, "A", create_v, 300),
        expected_aws_after_edit=lambda rows: values_match(rows, "A", edit_v, 600),
    )

# ---------------------------------------------------------------------------
# Native alias serviceTypes — exercise the composition's region-keyed zone-id
# mapping table (record.yaml lines 73-160). Custom is already covered.
# ---------------------------------------------------------------------------

def make_alias_cloudfront(suffix: str) -> Scenario:
    name = f"alias-cloudfront-{suffix}"
    record_name = f"e2e-{name}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="ALIAS",
        create_values={
            "routingPolicy": "simple",
            "serviceType": "CloudFront",
            "dnsName": "d111-create.cloudfront.net",
            "evaluateTargetHealth": False,
        },
        edit_values={
            "serviceType": "CloudFront",
            "dnsName": "d222-edit.cloudfront.net",
            "evaluateTargetHealth": False,
        },
        # CloudFront's hosted zone id is the well-known Z2FDTNDATAQYW2 — the
        # composition fills it in regardless of region. We only assert the DNS
        # name here because Route53's ListResourceRecordSets does not echo the
        # alias hosted-zone-id in our normalised rows.
        expected_aws=lambda rows: alias_match(rows, "d111-create.cloudfront.net", "Z2FDTNDATAQYW2"),
        expected_aws_after_edit=lambda rows: alias_match(rows, "d222-edit.cloudfront.net", "Z2FDTNDATAQYW2"),
    )

def make_alias_alb_us_east_1(suffix: str) -> Scenario:
    name = f"alias-alb-us-east-1-{suffix}"
    record_name = f"e2e-{name}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="ALIAS",
        create_values={
            "routingPolicy": "simple",
            "serviceType": "ALB",
            "dnsName": "alb-create-1234567.us-east-1.elb.amazonaws.com",
            "evaluateTargetHealth": True,
            "targetRegion": "us-east-1",
        },
        edit_values={
            "serviceType": "ALB",
            "dnsName": "alb-edit-1234567.us-east-1.elb.amazonaws.com",
            "evaluateTargetHealth": True,
            "targetRegion": "us-east-1",
        },
        # ALB us-east-1 = Z35SXDOTRQ7X7K
        expected_aws=lambda rows: alias_match(rows, "alb-create-1234567.us-east-1.elb.amazonaws.com", "Z35SXDOTRQ7X7K"),
        expected_aws_after_edit=lambda rows: alias_match(rows, "alb-edit-1234567.us-east-1.elb.amazonaws.com", "Z35SXDOTRQ7X7K"),
    )

def make_alias_nlb_us_east_1(suffix: str) -> Scenario:
    name = f"alias-nlb-us-east-1-{suffix}"
    record_name = f"e2e-{name}"
    return Scenario(
        name=name,
        record_name=record_name,
        record_type="ALIAS",
        create_values={
            "routingPolicy": "simple",
            "serviceType": "NLB",
            "dnsName": "nlb-create-1234567.elb.us-east-1.amazonaws.com",
            "evaluateTargetHealth": True,
            "targetRegion": "us-east-1",
        },
        edit_values={
            "serviceType": "NLB",
            "dnsName": "nlb-edit-1234567.elb.us-east-1.amazonaws.com",
            "evaluateTargetHealth": True,
            "targetRegion": "us-east-1",
        },
        # NLB us-east-1 = Z26RNL4JYFTOTI
        expected_aws=lambda rows: alias_match(rows, "nlb-create-1234567.elb.us-east-1.amazonaws.com", "Z26RNL4JYFTOTI"),
        expected_aws_after_edit=lambda rows: alias_match(rows, "nlb-edit-1234567.elb.us-east-1.amazonaws.com", "Z26RNL4JYFTOTI"),
    )

SCENARIO_BUILDERS: dict[str, Callable[[str], Scenario]] = {
    # baseline create+edit per record type (edit changes ttl AND values together)
    "a":          lambda s: make_a(s),
    "aaaa":       lambda s: make_aaaa(s),
    "cname":      lambda s: make_cname(s),
    "txt":        lambda s: make_txt(s),
    "mx":         lambda s: make_mx(s),
    "ptr":        lambda s: make_ptr(s),
    "srv":        lambda s: make_srv(s),
    "caa":        lambda s: make_caa(s),
    "ns":         lambda s: make_ns_subdelegation(s),
    "alias":      lambda s: make_alias_custom(s),
    "weighted-1": lambda s: make_weighted(s, "primary",   70, 50, ["10.0.5.10"], ["10.0.5.30"]),
    "weighted-2": lambda s: make_weighted(s, "secondary", 30, 50, ["10.0.5.20"], ["10.0.5.40"]),
    "failover-1": lambda s: make_failover(s, "primary",   "PRIMARY",   "10.0.6.10", "10.0.6.11"),
    "failover-2": lambda s: make_failover(s, "secondary", "SECONDARY", "10.0.6.20", "10.0.6.21"),
    "latency-1":  lambda s: make_latency(s, "us-east-1", "us-east-1", "10.0.7.10", "10.0.7.11"),
    "latency-2":  lambda s: make_latency(s, "eu-west-1", "eu-west-1", "10.0.7.20", "10.0.7.21"),
    "geo-1":      lambda s: make_geolocation(s, "EU", "EU", "10.0.8.10", "10.0.8.11"),
    "geo-2":      lambda s: make_geolocation(s, "NA", "NA", "10.0.8.20", "10.0.8.21"),
    "geoprox-1":  lambda s: make_geoproximity(s, "us-east-1", "us-east-1", "10.0.9.10", "10.0.9.11"),
    "geoprox-2":  lambda s: make_geoproximity(s, "eu-west-1", "eu-west-1", "10.0.9.20", "10.0.9.21"),
    "multi-1":    lambda s: make_multivalue(s, "host-1", "10.0.10.10", "10.0.10.11"),
    "multi-2":    lambda s: make_multivalue(s, "host-2", "10.0.10.20", "10.0.10.21"),
    # single-axis edits — exercise UPSERT on exactly one mutable field
    "a-ttl-only":            lambda s: make_a_ttl_only(s),
    "a-values-only":         lambda s: make_a_values_only(s),
    "weighted-weight-only":  lambda s: make_weighted_weight_only(s),
    # apex variant
    "a-apex":                lambda s: make_a_apex(s),
    # native alias serviceTypes — exercise the composition's hosted-zone-id
    # lookup tables for managed AWS endpoints
    "alias-cloudfront":      lambda s: make_alias_cloudfront(s),
    "alias-alb-us-east-1":   lambda s: make_alias_alb_us_east_1(s),
    "alias-nlb-us-east-1":   lambda s: make_alias_nlb_us_east_1(s),
}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", help="run only listed scenario keys (default: all)")
    ap.add_argument("--no-edit", action="store_true")
    ap.add_argument("--no-cleanup", action="store_true", help="leave files + AWS rows behind on success")
    ap.add_argument("--continue-on-fail", action="store_true")
    ap.add_argument("--suffix", default=str(int(time.time()))[-6:])
    args = ap.parse_args()

    keys = args.only if args.only else list(SCENARIO_BUILDERS.keys())
    unknown = [k for k in keys if k not in SCENARIO_BUILDERS]
    if unknown:
        print(f"unknown scenarios: {unknown}", file=sys.stderr)
        return 2

    suffix = args.suffix
    results: list[tuple[str, bool, str]] = []
    for key in keys:
        scenario = SCENARIO_BUILDERS[key](suffix)
        try:
            ok_run = run_scenario(scenario, do_edit=not args.no_edit, do_cleanup=not args.no_cleanup)
            results.append((scenario.name, ok_run, "" if ok_run else "scenario reported failure"))
        except subprocess.CalledProcessError as exc:
            results.append((scenario.name, False, f"subprocess: {exc}"))
            if not args.continue_on_fail:
                fail(f"stopping due to {scenario.name}")
                break
        except Exception as exc:
            results.append((scenario.name, False, f"exception: {exc}"))
            if not args.continue_on_fail:
                fail(f"stopping due to {scenario.name}")
                break
        if not results[-1][1] and not args.continue_on_fail:
            break

    print()
    print("=" * 60)
    print(f"{BOLD}SUMMARY{NC}")
    for name, ok_, msg in results:
        marker = f"{GREEN}PASS{NC}" if ok_ else f"{RED}FAIL{NC}"
        extra = f"  {msg}" if msg else ""
        print(f"  {marker}  {name}{extra}")
    failed = [r for r in results if not r[1]]
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
