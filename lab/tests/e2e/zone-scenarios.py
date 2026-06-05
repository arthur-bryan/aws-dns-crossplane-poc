#!/usr/bin/env python3
"""End-to-end zone-creation coverage. Tests every combination of public /
private, account, single / multiple VPC, and the cross-account VPC mix.
For each, validates:

  A. Hosted zone exists in the *right* AWS account (uses AssumeRole for dev)
  B. PrivateZone flag matches the request
  C. The full set of VPCs requested is attached (and only those)
  D. NS records appear in the parent zone (arthurbryan.com in prd-account)
  E. NS values in the parent match the authoritative NS records the new zone
     was assigned by AWS

Plus one negative: private zone with zero VPCs must be rejected at the
scaffolder layer.

Run:

    python3 lab/tests/e2e/zone-scenarios.py --continue-on-fail
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json as _json
import os
import subprocess
import sys
import time
from typing import Callable, Optional
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_spec = _ilu.spec_from_file_location("all_scenarios", os.path.join(HERE, "all-scenarios.py"))
_all = _ilu.module_from_spec(_spec)
sys.modules["all_scenarios"] = _all
_spec.loader.exec_module(_all)  # type: ignore[attr-defined]

ZONE_PARENT = _all.ZONE_NAME  # arthurbryan.com
PARENT_ZONE_ID = "Z03010981ALJFZB4QLU8W"
PARENT_ZONE_REF = _all.ZONE_REF
REPO_ROOT = _all.REPO_ROOT
GH_BRANCH = _all.GH_BRANCH

scaffolder_submit = _all.scaffolder_submit
scaffolder_wait = _all.scaffolder_wait
scaffolder_pr_url = _all.scaffolder_pr_url
scaffolder_log_tail = _all.scaffolder_log_tail
merge_pr = _all.merge_pr
argo_wait_revision = _all.argo_wait_revision
git_pull = _all.git_pull
step = _all.step
info = _all.info
ok = _all.ok
fail = _all.fail
run = _all.run

DEV_ACCOUNT_ROLE = "arn:aws:iam::309670275661:role/OrganizationAccountAccessRole"

VPC_PRD_DEFAULT = "vpc-0410f81cfe1bba322"
VPC_PRD_EXTRA   = "vpc-06c7bbc319e75e472"
VPC_DEV_DEFAULT = "vpc-0dd3eaef2e5c11f69"
VPC_DEV_EXTRA   = "vpc-0be51ad70cd373b81"


# ---------------------------------------------------------------------------
# AWS helpers (with optional cross-account creds)
# ---------------------------------------------------------------------------

def _aws_env(extra: Optional[dict] = None) -> dict:
    env = _all.aws_env()
    if extra:
        env.update(extra)
    return env


def _aws(extra: Optional[dict], *args: str):
    r = subprocess.run(
        ["aws", *args, "--output", "json"],
        check=True, capture_output=True, text=True, env=_aws_env(extra),
    )
    return _json.loads(r.stdout) if r.stdout else {}


def assume_role_creds(role_arn: str) -> dict:
    out = _aws(None, "sts", "assume-role", "--role-arn", role_arn,
               "--role-session-name", "e2e-zone-scenarios")
    c = out["Credentials"]
    return {
        "AWS_ACCESS_KEY_ID": c["AccessKeyId"],
        "AWS_SECRET_ACCESS_KEY": c["SecretAccessKey"],
        "AWS_SESSION_TOKEN": c["SessionToken"],
    }


def creds_for(account: str) -> Optional[dict]:
    return assume_role_creds(DEV_ACCOUNT_ROLE) if account == "dev-account" else None


def aws_find_zone(zone_fqdn: str, account: str) -> Optional[dict]:
    fqdn = zone_fqdn if zone_fqdn.endswith(".") else zone_fqdn + "."
    out = _aws(creds_for(account), "route53", "list-hosted-zones-by-name",
               "--dns-name", fqdn, "--max-items", "20")
    for z in out.get("HostedZones", []):
        if z["Name"] == fqdn:
            return z
    return None


def aws_get_zone(zone_id: str, account: str) -> dict:
    return _aws(creds_for(account), "route53", "get-hosted-zone", "--id", zone_id)


def aws_ns_in_parent(child_fqdn: str) -> list[str]:
    fqdn = child_fqdn if child_fqdn.endswith(".") else child_fqdn + "."
    out = _aws(
        None, "route53", "list-resource-record-sets",
        "--hosted-zone-id", PARENT_ZONE_ID,
        "--query", f"ResourceRecordSets[?Name=='{fqdn}' && Type=='NS']",
    )
    if not isinstance(out, list) or not out:
        return []
    return sorted(r["Value"].rstrip(".") for r in out[0]["ResourceRecords"])


# ---------------------------------------------------------------------------
# Cluster helpers (namespace-aware, mirroring multi-zone-scenarios.py)
# ---------------------------------------------------------------------------

def zone_xr_ready(xr_name: str, namespace: str) -> bool:
    r = subprocess.run(
        ["kubectl", "-n", namespace, "get",
         f"zone.dock.tech/{xr_name}", "-o", "json"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False
    obj = _json.loads(r.stdout)
    conds = {c["type"]: c["status"]
             for c in obj.get("status", {}).get("conditions") or []}
    return conds.get("Synced") == "True" and conds.get("Ready") == "True"


def wait_zone_ready(xr_name: str, namespace: str, deadline_s: int) -> bool:
    elapsed = 0
    while elapsed < deadline_s:
        if zone_xr_ready(xr_name, namespace):
            return True
        time.sleep(10)
        elapsed += 10
    return False


# ---------------------------------------------------------------------------
# Scaffolder submission
# ---------------------------------------------------------------------------

def submit_zone(prefix: str, environment: str, private: bool,
                vpc_refs: list[str]) -> Optional[str]:
    body = {
        "delegatedZone": PARENT_ZONE_REF,
        "prefix": prefix,
        "environment": environment,
        "private": private,
    }
    if private:
        body["vpcs"] = vpc_refs
    task_id = scaffolder_submit("template:default/dns-zone", body)
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        fail(f"scaffolder state={state}\n{log[-400:]}")
        return None
    return scaffolder_pr_url(task_id)


# ---------------------------------------------------------------------------
# Per-scenario invariants
# ---------------------------------------------------------------------------

def validate_zone(
    zone_fqdn: str, env: str, account: str, expect_private: bool,
    expect_vpc_ids: list[str],
) -> bool:
    # A. Zone exists in correct account
    z = aws_find_zone(zone_fqdn, account)
    if not z:
        fail(f"AWS Route 53 ({account}) does not show zone {zone_fqdn}")
        return False
    ok(f"AWS {account}: zone exists ({z['Id']})")
    zone_id_short = z["Id"].rsplit("/", 1)[-1]

    # B. Private/public flag
    if z.get("Config", {}).get("PrivateZone", False) != expect_private:
        fail(f"PrivateZone={z['Config']['PrivateZone']}, expected {expect_private}")
        return False
    ok(f"PrivateZone={expect_private}")

    # C. VPCs (private only)
    if expect_private:
        full = aws_get_zone(zone_id_short, account)
        attached = sorted(v["VPCId"] for v in full.get("VPCs", []))
        expected = sorted(set(expect_vpc_ids))
        if attached != expected:
            fail(f"VPC associations mismatch. attached={attached} expected={expected}")
            return False
        ok(f"VPCs attached: {attached}")

    # D. NS delegation exists in parent
    parent_ns = aws_ns_in_parent(zone_fqdn)
    if not parent_ns:
        fail(f"parent zone has no NS record for {zone_fqdn}")
        return False
    ok(f"parent NS delegation present ({len(parent_ns)} servers)")

    # E. Authoritative NS values match what's in the parent
    auth_ns_rows = _aws(
        creds_for(account), "route53", "list-resource-record-sets",
        "--hosted-zone-id", zone_id_short,
        "--query", f"ResourceRecordSets[?Name=='{zone_fqdn if zone_fqdn.endswith('.') else zone_fqdn+'.'}' && Type=='NS']",
    )
    if not auth_ns_rows:
        fail("authoritative zone is missing its own NS record set")
        return False
    auth_ns = sorted(r["Value"].rstrip(".") for r in auth_ns_rows[0]["ResourceRecords"])
    if auth_ns != parent_ns:
        fail(f"NS mismatch. parent={parent_ns} authoritative={auth_ns}")
        return False
    ok(f"NS values match between parent delegation and authoritative zone")
    return True


def create_and_validate(
    *, name: str, prefix: str, environment: str, private: bool,
    vpc_refs: list[str], account: str, expect_vpc_ids: list[str],
    deadline: int = 2400,
) -> bool:
    step(f"ZONE-CREATE {name} (env={environment}, private={private}, vpcs={len(vpc_refs)}, account={account})")
    new_zone = f"{prefix}.{ZONE_PARENT}"
    ns = f"system-infrastructure-{environment}"
    pr = submit_zone(prefix, environment, private, vpc_refs)
    if not pr:
        return False
    if not merge_pr(pr):
        return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync zone PR")
        return False
    info(f"waiting up to {deadline}s for zone-{new_zone} to reach Ready")
    if not wait_zone_ready(f"zone-{new_zone}", ns, deadline):
        fail(f"zone XR not Ready in {deadline}s")
        return False
    ok(f"zone-{new_zone} XR Ready")
    # AWS DNS propagation is usually fast within Route 53 console (seconds);
    # give a small grace window for the NS delegation record to land.
    time.sleep(15)
    return validate_zone(new_zone, environment, account, private, expect_vpc_ids)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def s_public_prd(suffix: str) -> bool:
    return create_and_validate(
        name="public-prd",
        prefix=f"e2e-zpub-prd-{suffix}",
        environment="prd",
        private=False,
        vpc_refs=[],
        account="prd-account",
        expect_vpc_ids=[],
    )


def s_public_dev(suffix: str) -> bool:
    return create_and_validate(
        name="public-dev",
        prefix=f"e2e-zpub-dev-{suffix}",
        environment="dev",
        private=False,
        vpc_refs=[],
        account="dev-account",
        expect_vpc_ids=[],
    )


def s_private_prd_default(suffix: str) -> bool:
    return create_and_validate(
        name="private-prd-default-vpc",
        prefix=f"e2e-zprv-prd-d-{suffix}",
        environment="prd",
        private=True,
        # User picks the default VPC explicitly (composition would have added
        # it anyway via deriveAccount). Tests dedupe behaviour.
        vpc_refs=[f"resource:default/{VPC_PRD_DEFAULT}"],
        account="prd-account",
        expect_vpc_ids=[VPC_PRD_DEFAULT],
    )


def s_private_prd_multi(suffix: str) -> bool:
    return create_and_validate(
        name="private-prd-multi-vpc",
        prefix=f"e2e-zprv-prd-m-{suffix}",
        environment="prd",
        private=True,
        vpc_refs=[
            f"resource:default/{VPC_PRD_DEFAULT}",
            f"resource:default/{VPC_PRD_EXTRA}",
        ],
        account="prd-account",
        expect_vpc_ids=[VPC_PRD_DEFAULT, VPC_PRD_EXTRA],
    )


def s_private_dev_default(suffix: str) -> bool:
    return create_and_validate(
        name="private-dev-default-vpc",
        prefix=f"e2e-zprv-dev-d-{suffix}",
        environment="dev",
        private=True,
        vpc_refs=[f"resource:default/{VPC_DEV_DEFAULT}"],
        account="dev-account",
        expect_vpc_ids=[VPC_DEV_DEFAULT],
    )


def s_private_dev_multi(suffix: str) -> bool:
    return create_and_validate(
        name="private-dev-multi-vpc",
        prefix=f"e2e-zprv-dev-m-{suffix}",
        environment="dev",
        private=True,
        vpc_refs=[
            f"resource:default/{VPC_DEV_DEFAULT}",
            f"resource:default/{VPC_DEV_EXTRA}",
        ],
        account="dev-account",
        expect_vpc_ids=[VPC_DEV_DEFAULT, VPC_DEV_EXTRA],
    )


def s_private_cross_account_vpc(suffix: str) -> bool:
    # Zone lives in prd-account, but ALSO associates a VPC owned by
    # dev-account. Crossplane handles cross-account VPC association via the
    # composition's VPCAssociationAuthorization + ZoneAssociation MRs.
    return create_and_validate(
        name="private-cross-account-vpc",
        prefix=f"e2e-zprv-xacct-{suffix}",
        environment="prd",
        private=True,
        vpc_refs=[
            f"resource:default/{VPC_PRD_DEFAULT}",
            f"resource:default/{VPC_DEV_DEFAULT}",
        ],
        account="prd-account",
        expect_vpc_ids=[VPC_PRD_DEFAULT, VPC_DEV_DEFAULT],
    )


def s_negative_private_zero_vpc(suffix: str) -> bool:
    step(f"ZONE-CREATE negative: private zone with 0 VPCs (suffix={suffix})")
    body = {
        "delegatedZone": PARENT_ZONE_REF,
        "prefix": f"e2e-zneg-{suffix}",
        "environment": "prd",
        "private": True,
        "vpcs": [],
    }
    try:
        task_id = scaffolder_submit("template:default/dns-zone", body)
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:240]
        ok(f"scaffolder rejected at submit: {msg}")
        return True
    state = scaffolder_wait(task_id)
    if state == "completed":
        fail("scaffolder accepted a private zone with 0 VPCs")
        return False
    log = "\n".join(scaffolder_log_tail(task_id))
    if "vpc" in log.lower() or "VPC" in log or "Private zones require" in log:
        ok(f"scaffolder rejected ({state}); log mentions VPC requirement")
        return True
    fail(f"scaffolder rejected but log didn't cite VPCs:\n{log[-300:]}")
    return False


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_zones(prefixes: list[tuple[str, str]]) -> None:
    """prefixes: list of (prefix, environment)."""
    paths: list[str] = []
    for prefix, env in prefixes:
        zone_fqdn = f"{prefix}.{ZONE_PARENT}"
        cat = f"entities/catalog/{env}/{zone_fqdn}"
        res = f"entities/environments/cross/cloud/infrastructure/{env}/resources/aws/{zone_fqdn}"
        for d in (cat, res):
            full = os.path.join(REPO_ROOT, d)
            if not os.path.isdir(full):
                continue
            for fn in os.listdir(full):
                paths.append(f"{d}/{fn}")
    paths = [p for p in paths if os.path.exists(os.path.join(REPO_ROOT, p))]
    if not paths:
        return
    branch = f"e2e-zone-cleanup-{int(time.time())}"
    try:
        run(["git", "-C", REPO_ROOT, "checkout", "-b", branch])
        run(["git", "-C", REPO_ROOT, "rm", *paths])
        run(["git", "-c", "user.name=Arthur Bryan", "-c",
             "user.email=arthurbryan2030@gmail.com", "-C", REPO_ROOT,
             "commit", "-m", f"chore(e2e-zone): cleanup {len(paths)} files"])
        run(["git", "-C", REPO_ROOT, "push", "-u", "origin", branch])
        pr_url = run([
            "gh", "pr", "create", "--base", GH_BRANCH, "--head", branch,
            "--title", "chore(e2e-zone): cleanup",
            "--body", "auto-cleanup from zone-scenarios",
        ]).stdout.strip()
        merge_pr(pr_url)
        git_pull()
    except Exception as e:
        info(f"cleanup PR best-effort failed: {e}")
    finally:
        try:
            run(["git", "-C", REPO_ROOT, "checkout", GH_BRANCH])
            run(["git", "-C", REPO_ROOT, "branch", "-D", branch], check=False)
        except Exception:
            pass


SCENARIOS: dict[str, Callable[[str], bool]] = {
    "public-prd":                s_public_prd,
    "public-dev":                s_public_dev,
    "private-prd-default-vpc":   s_private_prd_default,
    "private-prd-multi-vpc":     s_private_prd_multi,
    "private-dev-default-vpc":   s_private_dev_default,
    "private-dev-multi-vpc":     s_private_dev_multi,
    "private-cross-account-vpc": s_private_cross_account_vpc,
    "negative-private-zero-vpc": s_negative_private_zero_vpc,
}

# Which scenarios create which (prefix, env) pairs, for cleanup. The negative
# scenario doesn't create anything.
SCENARIO_TARGETS = {
    "public-prd":                ("e2e-zpub-prd",   "prd"),
    "public-dev":                ("e2e-zpub-dev",   "dev"),
    "private-prd-default-vpc":   ("e2e-zprv-prd-d", "prd"),
    "private-prd-multi-vpc":     ("e2e-zprv-prd-m", "prd"),
    "private-dev-default-vpc":   ("e2e-zprv-dev-d", "dev"),
    "private-dev-multi-vpc":     ("e2e-zprv-dev-m", "dev"),
    "private-cross-account-vpc": ("e2e-zprv-xacct", "prd"),
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
        print(f"unknown: {unknown}", file=sys.stderr)
        return 2

    results: list[tuple[str, bool]] = []
    targets: list[tuple[str, str]] = []
    for n in names:
        try:
            passed = SCENARIOS[n](args.suffix)
        except Exception as e:
            fail(f"{n} raised: {type(e).__name__}: {e}")
            passed = False
        results.append((n, passed))
        if n in SCENARIO_TARGETS:
            prefix, env = SCENARIO_TARGETS[n]
            targets.append((f"{prefix}-{args.suffix}", env))
        if not passed and not args.continue_on_fail:
            break

    if not args.no_cleanup and targets:
        info(f"cleaning up {len(targets)} test zones …")
        cleanup_zones(targets)

    print()
    print("=" * 60)
    print("SUMMARY")
    for n, p in results:
        tag = "\033[0;32mPASS\033[0m" if p else "\033[0;31mFAIL\033[0m"
        print(f"  {tag}  {n}")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
