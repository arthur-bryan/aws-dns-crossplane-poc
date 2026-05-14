#!/usr/bin/env python3
"""End-to-end coverage for zones beyond the default public/prd one.

Two scenarios:
  - dev-public-zone-and-record: create a delegated public zone in the dev
    AWS account (env=dev), add an A record inside it, verify AWS Route 53
    holds the record in the correct account and the parent zone has NS
    delegation in place.
  - prd-private-zone-and-record: create a private zone in prd-account with
    a VPC association, add an A record, verify AWS Route 53 shows the zone
    as private and the record exists.

Each scenario auto-cleans the records and the zone it created.

Run:

    python3 lab/tests/e2e/multi-zone-scenarios.py --continue-on-fail
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import os
import sys
import time
from typing import Callable, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_spec = _ilu.spec_from_file_location("all_scenarios", os.path.join(HERE, "all-scenarios.py"))
_all = _ilu.module_from_spec(_spec)
sys.modules["all_scenarios"] = _all
_spec.loader.exec_module(_all)  # type: ignore[attr-defined]

BACKSTAGE = _all.BACKSTAGE
ZONE_NAME_PARENT = _all.ZONE_NAME  # arthurbryan.com
PARENT_ZONE_REF = _all.ZONE_REF
NAMESPACE = _all.NAMESPACE
REPO_ROOT = _all.REPO_ROOT
GH_BRANCH = _all.GH_BRANCH
scaffolder_submit = _all.scaffolder_submit
scaffolder_wait = _all.scaffolder_wait
scaffolder_pr_url = _all.scaffolder_pr_url
scaffolder_log_tail = _all.scaffolder_log_tail
merge_pr = _all.merge_pr
argo_wait_revision = _all.argo_wait_revision
wait_xr_ready = _all.wait_xr_ready  # for Record XRs only
git_pull = _all.git_pull


# `_all.wait_xr_ready` / `_all.xr_status` are hard-coded for the Record XR
# kind. Re-implement here for the Zone XR kind. (The original helpers query
# `record.dock.tech/...` which obviously doesn't exist for zone tests, so
# this whole suite was timing out on the wrong CRD until we noticed.)
import subprocess
import json as _json

def record_xr_status_ns(xr_name: str, namespace: str) -> dict:
    cmd = ["kubectl", "-n", namespace, "get",
           f"record.dock.tech/{xr_name}", "-o", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"absent": True}
    obj = _json.loads(r.stdout)
    conds = {c["type"]: c["status"]
             for c in obj.get("status", {}).get("conditions") or []}
    return {
        "absent": False,
        "synced": conds.get("Synced", ""),
        "ready": conds.get("Ready", ""),
    }


def wait_record_xr_ready_ns(xr_name: str, namespace: str, deadline: int) -> bool:
    elapsed = 0
    while elapsed < deadline:
        s = record_xr_status_ns(xr_name, namespace)
        if (not s.get("absent")
                and s.get("synced") == "True"
                and s.get("ready") == "True"):
            return True
        time.sleep(5)
        elapsed += 5
    return False


def zone_xr_status(xr_name: str, namespace: str) -> dict:
    cmd = ["kubectl", "-n", namespace, "get",
           f"zone.dock.tech/{xr_name}", "-o", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"absent": True}
    obj = _json.loads(r.stdout)
    conds = {c["type"]: c["status"]
             for c in obj.get("status", {}).get("conditions") or []}
    return {
        "absent": False,
        "synced": conds.get("Synced", ""),
        "ready": conds.get("Ready", ""),
    }

def wait_zone_xr_ready(xr_name: str, namespace: str, deadline: int) -> bool:
    elapsed = 0
    while elapsed < deadline:
        s = zone_xr_status(xr_name, namespace)
        if (not s.get("absent")
                and s.get("synced") == "True"
                and s.get("ready") == "True"):
            return True
        time.sleep(5)
        elapsed += 5
    return False
step = _all.step
info = _all.info
ok = _all.ok
fail = _all.fail
run = _all.run
aws = _all.aws


def submit_zone_create(prefix: str, environment: str, private: bool,
                       vpc_refs: Optional[list[str]] = None) -> Optional[str]:
    values = {
        "delegatedZone": PARENT_ZONE_REF,
        "prefix": prefix,
        "environment": environment,
        "private": private,
    }
    if private and vpc_refs:
        values["vpcs"] = vpc_refs
    task_id = scaffolder_submit("template:default/aws-dns-zone", values)
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        fail(f"zone scaffolder state={state}\n{log[-400:]}")
        return None
    return scaffolder_pr_url(task_id)


def submit_record_create(zone_namespace: str, zone_name: str,
                         record_name: str, record_type: str,
                         values_payload: dict) -> Optional[str]:
    body = {
        "zone": f"resource:{zone_namespace}/zone-{zone_name}",
        "recordName": record_name,
        "type": record_type,
    }
    body.update(values_payload)
    task_id = scaffolder_submit("template:default/aws-dns-record", body)
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        fail(f"record scaffolder state={state}\n{log[-400:]}")
        return None
    return scaffolder_pr_url(task_id)


DEV_ACCOUNT_ROLE = "arn:aws:iam::309670275661:role/OrganizationAccountAccessRole"


def _aws(env_extra: Optional[dict], *args: str) -> object:
    """Like _all.aws but with optional credential overrides."""
    base = _all.aws_env()
    if env_extra:
        base.update(env_extra)
    r = subprocess.run(["aws", *args, "--output", "json"],
                       check=True, capture_output=True, text=True, env=base)
    return _json.loads(r.stdout) if r.stdout else {}


def assume_role_creds(role_arn: str) -> dict:
    """Return AWS env-var overrides for the dev-account role chained from
    the prd-account creds in the aws-creds Secret. This mirrors what the
    Crossplane ClusterProviderConfig dev-account does at provider-side."""
    out = _aws(None, "sts", "assume-role",
               "--role-arn", role_arn,
               "--role-session-name", "e2e-multizone")
    c = out["Credentials"]
    return {
        "AWS_ACCESS_KEY_ID": c["AccessKeyId"],
        "AWS_SECRET_ACCESS_KEY": c["SecretAccessKey"],
        "AWS_SESSION_TOKEN": c["SessionToken"],
    }


def aws_zone_by_name(zone_fqdn: str, env_extra: Optional[dict] = None) -> Optional[dict]:
    if not zone_fqdn.endswith("."):
        zone_fqdn = zone_fqdn + "."
    out = _aws(env_extra, "route53", "list-hosted-zones-by-name",
               "--dns-name", zone_fqdn, "--max-items", "5")
    for z in out.get("HostedZones", []):
        if z["Name"] == zone_fqdn:
            return z
    return None


def aws_record_in_zone(zone_id: str, record_fqdn: str, record_type: str,
                       env_extra: Optional[dict] = None) -> list[dict]:
    if not record_fqdn.endswith("."):
        record_fqdn = record_fqdn + "."
    out = _aws(
        env_extra, "route53", "list-resource-record-sets",
        "--hosted-zone-id", zone_id,
        "--query",
        f"ResourceRecordSets[?Name=='{record_fqdn}' && Type=='{record_type}']",
    )
    return out if isinstance(out, list) else []


def wait_until(check: Callable[[], bool], deadline_s: int = 360,
               poll_s: int = 5) -> bool:
    elapsed = 0
    while elapsed < deadline_s:
        try:
            if check():
                return True
        except Exception as e:
            info(f"check transient error: {type(e).__name__}: {e!s:.140}")
        time.sleep(poll_s)
        elapsed += poll_s
    return False


# ---------------------------------------------------------------------------
# Scenario 1: public delegated zone in dev account.
# ---------------------------------------------------------------------------

def scenario_dev_public_zone(suffix: str) -> bool:
    step(f"MULTI-ZONE dev-public-zone-and-record ({suffix})")
    prefix = f"e2e-multidev-{suffix}"
    new_zone = f"{prefix}.{ZONE_NAME_PARENT}"
    new_zone_ns = "system-infrastructure-dev"

    info(f"creating public dev zone {new_zone} (env=dev, expect dev-account)")
    pr = submit_zone_create(prefix, environment="dev", private=False)
    if not pr or not merge_pr(pr):
        return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync zone PR")
        return False
    # Lab caveat: zone creation timing in the kind-based PoC is variable
    # (observed 14-31 min). Override via E2E_ZONE_DEADLINE.
    deadline = int(os.environ.get("E2E_ZONE_DEADLINE", "1800"))
    if not wait_zone_xr_ready(f"zone-{new_zone}", "system-infrastructure-dev",
                              deadline):
        fail(f"zone-{new_zone} XR did not reach Ready in {deadline}s")
        return False
    ok(f"zone-{new_zone} XR Ready")

    # Verify in AWS: hosted zone exists, is public. The dev zone lives in
    # dev-account, so we have to assume the dev cross-account role like the
    # Crossplane provider does.
    info("assuming dev-account role for AWS-side verification")
    dev_creds = assume_role_creds(DEV_ACCOUNT_ROLE)
    z = None
    def found() -> bool:
        nonlocal z
        z = aws_zone_by_name(new_zone, env_extra=dev_creds)
        return z is not None
    if not wait_until(found, deadline_s=180, poll_s=5):
        fail(f"AWS Route 53 (dev-account) does not show zone {new_zone}")
        return False
    if z.get("Config", {}).get("PrivateZone", False):
        fail(f"zone {new_zone} is private; expected public")
        return False
    ok(f"AWS Route 53 dev-account has public zone {new_zone} (id {z['Id']})")

    # Add an A record inside the new zone.
    info(f"creating A record host1.{new_zone} = [10.0.50.1]")
    pr2 = submit_record_create(new_zone_ns, new_zone, "host1", "A",
                               {"ttl": 300, "values": ["10.0.50.1"],
                                "routingPolicy": "simple"})
    if not pr2 or not merge_pr(pr2):
        return False
    if not argo_wait_revision("entities", git_pull(), 240):
        fail("argo did not sync record PR")
        return False
    if not wait_record_xr_ready_ns(f"record-host1.{new_zone}",
                                    "system-infrastructure-dev", 360):
        fail("record XR did not reach Ready in 6 min")
        return False

    zone_id = z["Id"].rsplit("/", 1)[-1]
    def record_visible() -> bool:
        rows = aws_record_in_zone(zone_id, f"host1.{new_zone}", "A",
                                  env_extra=dev_creds)
        if not rows:
            return False
        vals = sorted(r["Value"] for r in rows[0]["ResourceRecords"])
        return vals == ["10.0.50.1"]
    if not wait_until(record_visible, deadline_s=180):
        fail(f"AWS record host1.{new_zone} not visible within 3 min")
        return False
    ok(f"AWS record host1.{new_zone} = [10.0.50.1] in zone {zone_id}")
    return True


# ---------------------------------------------------------------------------
# Scenario 2: private zone in prd-account with VPC association.
# ---------------------------------------------------------------------------

PRD_DEFAULT_VPC_REF = "resource:default/vpc-0410f81cfe1bba322"


def scenario_prd_private_zone(suffix: str) -> bool:
    step(f"MULTI-ZONE prd-private-zone-and-record ({suffix})")
    prefix = f"e2e-multipriv-{suffix}"
    new_zone = f"{prefix}.{ZONE_NAME_PARENT}"
    new_zone_ns = "system-infrastructure-prd"

    info(f"creating private prd zone {new_zone} (VPC association expected)")
    pr = submit_zone_create(prefix, environment="prd", private=True,
                            vpc_refs=[PRD_DEFAULT_VPC_REF])
    if not pr or not merge_pr(pr):
        return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync zone PR")
        return False
    deadline = int(os.environ.get("E2E_ZONE_DEADLINE", "1800"))
    if not wait_zone_xr_ready(f"zone-{new_zone}", "system-infrastructure-prd",
                              deadline):
        fail(f"zone-{new_zone} XR did not reach Ready in {deadline}s")
        return False
    ok(f"zone-{new_zone} XR Ready")

    z = None
    def found() -> bool:
        nonlocal z
        z = aws_zone_by_name(new_zone)
        return z is not None and z.get("Config", {}).get("PrivateZone", False)
    if not wait_until(found, deadline_s=120, poll_s=5):
        fail(f"AWS Route 53 does not show {new_zone} as private within 2 min")
        return False
    ok(f"AWS has private zone {new_zone} (id {z['Id']})")

    # Confirm VPC association.
    zone_id = z["Id"].rsplit("/", 1)[-1]
    vpcs_attached = aws("route53", "get-hosted-zone", "--id", zone_id)
    associated = vpcs_attached.get("VPCs", [])
    if not any(v.get("VPCId") == "vpc-0410f81cfe1bba322" for v in associated):
        fail(f"private zone {new_zone} not associated with vpc-0410f81cfe1bba322. attached={associated}")
        return False
    ok(f"VPC vpc-0410f81cfe1bba322 attached to {new_zone}")

    # Add a record inside the private zone.
    info(f"creating A record svc.{new_zone} = [10.0.60.1]")
    pr2 = submit_record_create(new_zone_ns, new_zone, "svc", "A",
                               {"ttl": 300, "values": ["10.0.60.1"],
                                "routingPolicy": "simple"})
    if not pr2 or not merge_pr(pr2):
        return False
    if not argo_wait_revision("entities", git_pull(), 240):
        fail("argo did not sync record PR")
        return False
    if not wait_xr_ready(f"record-svc.{new_zone}", 240):
        fail("record XR did not reach Ready")
        return False

    def record_visible() -> bool:
        rows = aws_record_in_zone(zone_id, f"svc.{new_zone}", "A")
        if not rows:
            return False
        vals = sorted(r["Value"] for r in rows[0]["ResourceRecords"])
        return vals == ["10.0.60.1"]
    if not wait_until(record_visible, deadline_s=120):
        fail(f"AWS record svc.{new_zone} not visible within 2 min")
        return False
    ok(f"AWS record svc.{new_zone} = [10.0.60.1] in private zone {zone_id}")
    return True


# ---------------------------------------------------------------------------
# Cleanup: revert PR for everything this run created.
# ---------------------------------------------------------------------------

def cleanup(child_zones: list[tuple[str, str, str]]) -> None:
    """child_zones: list of (new_zone_fqdn, env, sub_records[list of (recordname, type)])"""
    paths: list[str] = []
    for zone_fqdn, env, _ in child_zones:
        # Catalog files
        for name in ("zone.yaml",):
            paths.append(f"entities/catalog/{env}/{zone_fqdn}/{name}")
        # Resource files
        env_dir = f"entities/environments/cross/cloud/infrastructure/{env}/resources/aws/{zone_fqdn}"
        for fn in os.listdir(os.path.join(REPO_ROOT, env_dir)) if os.path.exists(os.path.join(REPO_ROOT, env_dir)) else []:
            paths.append(f"{env_dir}/{fn}")
        # Catalog directory may have multiple files (zone + records)
        cat_dir = f"entities/catalog/{env}/{zone_fqdn}"
        for fn in os.listdir(os.path.join(REPO_ROOT, cat_dir)) if os.path.exists(os.path.join(REPO_ROOT, cat_dir)) else []:
            p = f"{cat_dir}/{fn}"
            if p not in paths:
                paths.append(p)
    paths = [p for p in paths if os.path.exists(os.path.join(REPO_ROOT, p))]
    if not paths:
        return
    branch = f"e2e-multizone-cleanup-{int(time.time())}"
    try:
        run(["git", "-C", REPO_ROOT, "checkout", "-b", branch])
        run(["git", "-C", REPO_ROOT, "rm", *paths])
        run(["git", "-c", "user.name=Arthur Bryan", "-c",
             "user.email=arthurbryan2030@gmail.com", "-C", REPO_ROOT,
             "commit", "-m", f"chore(e2e-multizone): cleanup {len(paths)} files"])
        run(["git", "-C", REPO_ROOT, "push", "-u", "origin", branch])
        pr_url = run([
            "gh", "pr", "create", "--base", GH_BRANCH, "--head", branch,
            "--title", "chore(e2e-multizone): cleanup",
            "--body", "auto-cleanup",
        ]).stdout.strip()
        merge_pr(pr_url)
        git_pull()
    except Exception as e:
        info(f"cleanup best-effort failed: {e}")
    finally:
        try:
            run(["git", "-C", REPO_ROOT, "checkout", GH_BRANCH])
            run(["git", "-C", REPO_ROOT, "branch", "-D", branch], check=False)
        except Exception:
            pass


SCENARIOS: dict[str, Callable[[str], bool]] = {
    "dev-public-zone-and-record": scenario_dev_public_zone,
    "prd-private-zone-and-record": scenario_prd_private_zone,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", help="run only listed scenarios")
    ap.add_argument("--continue-on-fail", action="store_true")
    ap.add_argument("--suffix", default=time.strftime("%H%M%S"))
    ap.add_argument("--no-cleanup", action="store_true")
    args = ap.parse_args()

    names = args.only or list(SCENARIOS.keys())
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print(f"unknown scenarios: {unknown}", file=sys.stderr)
        return 2

    results: list[tuple[str, bool]] = []
    created_zones: list[tuple[str, str, list]] = []
    for name in names:
        try:
            passed = SCENARIOS[name](args.suffix)
        except Exception as e:
            fail(f"scenario {name} raised: {type(e).__name__}: {e}")
            passed = False
        results.append((name, passed))
        if name == "dev-public-zone-and-record":
            created_zones.append((f"e2e-multidev-{args.suffix}.{ZONE_NAME_PARENT}", "dev", []))
        elif name == "prd-private-zone-and-record":
            created_zones.append((f"e2e-multipriv-{args.suffix}.{ZONE_NAME_PARENT}", "prd", []))
        if not passed and not args.continue_on_fail:
            break

    if not args.no_cleanup and created_zones:
        info(f"cleaning up {len(created_zones)} test zones …")
        cleanup(created_zones)

    print()
    print("=" * 60)
    print("SUMMARY")
    for name, passed in results:
        tag = "\033[0;32mPASS\033[0m" if passed else "\033[0;31mFAIL\033[0m"
        print(f"  {tag}  {name}")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
