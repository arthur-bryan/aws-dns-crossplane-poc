#!/usr/bin/env python3
"""End-to-end negative tests: scenarios with invalid input that *should* be
rejected somewhere along the platform chain. Each scenario declares where the
rejection is expected (scaffolder schema validation, or AWS Route 53 backend)
and asserts the platform actually rejects it.

Run:

    python3 lab/tests/e2e/negative-scenarios.py --continue-on-fail
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Reuse the helpers from the positive-test runner so we don't duplicate auth,
# Backstage URL discovery, etc.
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("all_scenarios", os.path.join(HERE, "all-scenarios.py"))
_all = _ilu.module_from_spec(_spec)
# Register before exec so @dataclass can find this module in sys.modules.
sys.modules["all_scenarios"] = _all
_spec.loader.exec_module(_all)  # type: ignore[attr-defined]

BACKSTAGE = _all.BACKSTAGE
ZONE_REF = _all.ZONE_REF
ZONE_NAME = _all.ZONE_NAME
NAMESPACE = _all.NAMESPACE
http_json = _all.http_json
backstage_token = _all.backstage_token
scaffolder_submit = _all.scaffolder_submit
scaffolder_wait = _all.scaffolder_wait
scaffolder_task = _all.scaffolder_task
scaffolder_log_tail = _all.scaffolder_log_tail
scaffolder_pr_url = _all.scaffolder_pr_url
merge_pr = _all.merge_pr
post_merge_validate = _all.post_merge_validate
xr_status = _all.xr_status
mr_status = _all.mr_status
step = _all.step
info = _all.info
ok = _all.ok
fail = _all.fail
run = _all.run
git_pull = _all.git_pull


@dataclass
class NegativeScenario:
    name: str
    description: str
    record_name: str
    record_type: str
    values: dict
    # One of: "scaffolder" (schema/validation rejects), "aws" (PR merges but
    # MR ends up Synced=False with matching message from Route 53).
    expected_failure: str
    expected_message_regex: str
    set_identifier: Optional[str] = None


def _key(scen: NegativeScenario) -> str:
    base = (scen.record_name or "apex").replace(".", "-")
    if scen.set_identifier:
        return f"{base}-{scen.set_identifier}"
    return base


def assert_scaffolder_rejects(scen: NegativeScenario) -> bool:
    body = {
        "zone": ZONE_REF,
        "recordName": scen.record_name,
        "type": scen.record_type,
    }
    body.update(scen.values)
    try:
        task_id = scaffolder_submit("template:default/aws-dns-record", body)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if re.search(scen.expected_message_regex, raw, re.IGNORECASE):
            ok(f"scaffolder API rejected at submit: {raw[:120]}")
            return True
        fail(f"scaffolder rejected but message didn't match: {raw[:200]}")
        return False
    state = scaffolder_wait(task_id)
    if state == "completed":
        fail(f"task {task_id} completed but we expected scaffolder rejection")
        # Best-effort cleanup of the PR Backstage just opened.
        try:
            pr = scaffolder_pr_url(task_id)
            if pr:
                info(f"closing accidentally-created PR {pr}")
                run(["gh", "pr", "close", pr, "--delete-branch"], check=False)
        except Exception:
            pass
        return False
    if state == "timeout":
        fail(f"scaffolder task {task_id} timed out")
        return False
    log = "\n".join(scaffolder_log_tail(task_id))
    if re.search(scen.expected_message_regex, log, re.IGNORECASE):
        ok(f"scaffolder rejected ({state}); log matched regex")
        return True
    fail(f"scaffolder failed but message didn't match. log tail:\n{log[-500:]}")
    return False


def assert_aws_rejects(scen: NegativeScenario) -> bool:
    """Submit, wait for PR, merge, then verify the MR lands in Synced=False
    with a Route 53 error matching the regex. Auto-cleans the YAML afterwards
    via a revert PR so the failed test record doesn't linger."""
    body = {
        "zone": ZONE_REF,
        "recordName": scen.record_name,
        "type": scen.record_type,
    }
    body.update(scen.values)
    try:
        task_id = scaffolder_submit("template:default/aws-dns-record", body)
    except urllib.error.HTTPError as e:
        fail(f"expected AWS rejection but scaffolder API errored at submit: {e.read().decode()[:200]}")
        return False
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        fail(f"expected AWS rejection but scaffolder task {state}: {log[-400:]}")
        return False
    pr = scaffolder_pr_url(task_id)
    if not pr:
        fail(f"no PR URL on task {task_id}")
        return False
    info(f"PR: {pr}; merging to send invalid input downstream")
    if not merge_pr(pr):
        fail("merge_pr returned False")
        return False
    git_pull()
    # Wait up to 5 minutes for MR to show the expected AWS error.
    key = _key(scen)
    xr_name = f"record-{key}.{ZONE_NAME}"
    deadline = 300
    elapsed = 0
    while elapsed < deadline:
        m = mr_status(xr_name) or {}
        msg = m.get("synced_msg", "") or ""
        if m.get("synced") == "False" and re.search(scen.expected_message_regex, msg, re.IGNORECASE):
            ok(f"AWS rejected: {msg[:160]}")
            cleanup_pr(scen, xr_name)
            return True
        time.sleep(5)
        elapsed += 5
    s = xr_status(xr_name)
    m = mr_status(xr_name)
    fail(f"AWS did not reject within {deadline}s. XR={s} MR={m}")
    cleanup_pr(scen, xr_name)
    return False


def cleanup_pr(scen: NegativeScenario, xr_name: str) -> None:
    """Open and auto-merge a revert PR that removes the bad XR + catalog files
    so leftover failure state doesn't pollute the cluster between runs."""
    repo_root = _all.REPO_ROOT
    zone_env = _all.ZONE_ENVIRONMENT
    key = _key(scen)
    xr_rel = _all.xr_path(ZONE_NAME, key)
    cat_rel = _all.catalog_path(zone_env, ZONE_NAME, key)
    if not os.path.exists(os.path.join(repo_root, xr_rel)):
        return
    branch = f"e2e-negative-cleanup-{key}-{int(time.time())}"
    try:
        run(["git", "-C", repo_root, "checkout", "-b", branch])
        run(["git", "-C", repo_root, "rm", xr_rel, cat_rel])
        run(["git", "-c", "user.name=Arthur Bryan", "-c",
             "user.email=arthurbryan2030@gmail.com",
             "-C", repo_root, "commit", "-m",
             f"chore(e2e-negative): cleanup {scen.name}"])
        run(["git", "-C", repo_root, "push", "-u", "origin", branch])
        pr = run(["gh", "pr", "create", "--base", _all.GH_BRANCH, "--head",
                  branch, "--title", f"chore(e2e-negative): cleanup {scen.name}",
                  "--body", "auto-cleanup from negative-scenarios test"]).stdout.strip()
        merge_pr(pr)
        git_pull()
    except Exception as e:
        info(f"cleanup PR best-effort failed: {e}")
    finally:
        try:
            run(["git", "-C", repo_root, "checkout", _all.GH_BRANCH])
            run(["git", "-C", repo_root, "branch", "-D", branch], check=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Negative scenarios
# ---------------------------------------------------------------------------

SCENARIOS: list[NegativeScenario] = [
    # Schema-enforced bounds: --------------------------------------------------
    NegativeScenario(
        name="ttl-below-minimum",
        description="TTL=5 should be rejected (schema minimum=60)",
        record_name=f"neg-ttl-low",
        record_type="A",
        values={"ttl": 5, "values": ["192.0.2.1"], "routingPolicy": "simple"},
        expected_failure="scaffolder",
        expected_message_regex=r"ttl|minimum",
    ),
    NegativeScenario(
        name="ttl-above-maximum",
        description="TTL=999999999 should be rejected (schema maximum=604800)",
        record_name=f"neg-ttl-high",
        record_type="A",
        values={"ttl": 999999999, "values": ["192.0.2.1"], "routingPolicy": "simple"},
        expected_failure="scaffolder",
        expected_message_regex=r"ttl|maximum",
    ),
    NegativeScenario(
        name="a-non-ip-value",
        description="A record with 'notanip' should be rejected (regex on values)",
        record_name=f"neg-a-bad-value",
        record_type="A",
        values={"ttl": 300, "values": ["notanip"], "routingPolicy": "simple"},
        expected_failure="scaffolder",
        expected_message_regex=r"values|pattern",
    ),
    NegativeScenario(
        name="mx-missing-priority",
        description="MX with no priority should be rejected (regex requires '<n> <host>')",
        record_name=f"neg-mx-bad",
        record_type="MX",
        values={"ttl": 300, "values": ["mail.example.com"], "routingPolicy": "simple"},
        expected_failure="scaffolder",
        expected_message_regex=r"values|pattern|mx",
    ),
    NegativeScenario(
        name="srv-malformed",
        description="SRV without 4 fields should be rejected (regex)",
        record_name=f"neg-srv-bad",
        record_type="SRV",
        values={"ttl": 300, "values": ["10 target.example.com"], "routingPolicy": "simple"},
        expected_failure="scaffolder",
        expected_message_regex=r"values|pattern|srv",
    ),
    # AWS-side rejections: -----------------------------------------------------
    NegativeScenario(
        name="a-octet-out-of-range",
        description="A record with octet > 255 passes the regex but AWS Route 53 rejects",
        record_name=f"neg-a-bad-octet",
        record_type="A",
        values={"ttl": 300, "values": ["999.999.999.999"], "routingPolicy": "simple"},
        expected_failure="aws",
        expected_message_regex=r"InvalidChangeBatch|InvalidInput|invalid|IP",
    ),
]


def run_scenario(scen: NegativeScenario) -> bool:
    step(f"NEGATIVE {scen.name} — {scen.description}")
    if scen.expected_failure == "scaffolder":
        return assert_scaffolder_rejects(scen)
    if scen.expected_failure == "aws":
        return assert_aws_rejects(scen)
    fail(f"unknown expected_failure={scen.expected_failure!r}")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", help="run only listed scenarios")
    ap.add_argument("--continue-on-fail", action="store_true")
    args = ap.parse_args()

    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in SCENARIOS if s.name in args.only]
        missing = set(args.only) - {s.name for s in scenarios}
        if missing:
            print(f"unknown scenarios: {sorted(missing)}", file=sys.stderr)
            return 2

    results: list[tuple[str, bool]] = []
    for scen in scenarios:
        try:
            passed = run_scenario(scen)
        except Exception as e:
            fail(f"scenario {scen.name} raised: {type(e).__name__}: {e}")
            passed = False
        results.append((scen.name, passed))
        if not passed and not args.continue_on_fail:
            break

    print()
    print("=" * 60)
    print("SUMMARY")
    for name, passed in results:
        tag = "\033[0;32mPASS\033[0m" if passed else "\033[0;31mFAIL\033[0m"
        print(f"  {tag}  {name}")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
