#!/usr/bin/env python3
"""End-to-end concurrency tests for the DNS platform.

Validates the platform handles multiple in-flight changes without torn state:
- two edits to the same record fired back-to-back;
- routing-policy sibling records edited in parallel;
- the "sibling TTL must match" Route 53 constraint, where the first sibling's
  update will fail until the second sibling's update lands.

Each scenario uses a fresh suffix so it doesn't collide with the create-only
suite. All cleanup happens at the end of the script.

Run:

    python3 lab/tests/e2e/concurrency-scenarios.py --continue-on-fail
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_spec = _ilu.spec_from_file_location("all_scenarios", os.path.join(HERE, "all-scenarios.py"))
_all = _ilu.module_from_spec(_spec)
sys.modules["all_scenarios"] = _all
_spec.loader.exec_module(_all)  # type: ignore[attr-defined]

# Re-export the bits we need.
BACKSTAGE = _all.BACKSTAGE
ZONE_REF = _all.ZONE_REF
ZONE_NAME = _all.ZONE_NAME
NAMESPACE = _all.NAMESPACE
ZONE_ENVIRONMENT = _all.ZONE_ENVIRONMENT
REPO_ROOT = _all.REPO_ROOT
GH_BRANCH = _all.GH_BRANCH
scaffolder_submit = _all.scaffolder_submit
scaffolder_wait = _all.scaffolder_wait
scaffolder_pr_url = _all.scaffolder_pr_url
scaffolder_log_tail = _all.scaffolder_log_tail
merge_pr = _all.merge_pr
argo_wait_revision = _all.argo_wait_revision
wait_xr_ready = _all.wait_xr_ready
mr_status = _all.mr_status
aws_records_at = _all.aws_records_at
git_pull = _all.git_pull
base_key = _all.base_key
xr_path = _all.xr_path
catalog_path = _all.catalog_path
step = _all.step
info = _all.info
ok = _all.ok
fail = _all.fail
run = _all.run


# ---------------------------------------------------------------------------
# Tiny helpers for parallel scaffolder submission. PR merge is intentionally
# serialised: GitHub allows only one merge-to-default at a time anyway, and we
# want to exercise "two changes land sequentially after concurrent submission",
# not "two simultaneous force-pushes".
# ---------------------------------------------------------------------------

print_lock = threading.Lock()


def _p(msg: str) -> None:
    with print_lock:
        print(msg, flush=True)


def submit_record_create(
    record_name: str, record_type: str, values: dict
) -> Optional[str]:
    body = {"zone": ZONE_REF, "recordName": record_name, "type": record_type}
    body.update(values)
    task_id = scaffolder_submit("template:default/aws-dns-record", body)
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        _p(f"  [fail] create scaffolder state={state} log:\n{log[-300:]}")
        return None
    return scaffolder_pr_url(task_id)


def submit_record_edit(
    record_name: str, record_type: str, values: dict,
    set_identifier: Optional[str] = None,
) -> Optional[str]:
    body = {"zone": ZONE_REF, "recordName": record_name, "type": record_type}
    if set_identifier:
        body["setIdentifier"] = set_identifier
    body.update(values)
    task_id = scaffolder_submit("template:default/aws-dns-record-edit", body)
    state = scaffolder_wait(task_id)
    if state != "completed":
        log = "\n".join(scaffolder_log_tail(task_id))
        _p(f"  [fail] edit scaffolder state={state} log:\n{log[-300:]}")
        return None
    return scaffolder_pr_url(task_id)


def wait_until(check: Callable[[], bool], deadline_s: int = 360, poll_s: int = 5) -> bool:
    """Like a plain poll, but swallows transient exceptions inside the check
    (e.g. AWS CLI returning 254 from throttling) and keeps trying."""
    elapsed = 0
    while elapsed < deadline_s:
        try:
            if check():
                return True
        except Exception as e:
            _p(f"  [info] check transient error ({type(e).__name__}: {e!s:.120}); retrying")
        time.sleep(poll_s)
        elapsed += poll_s
    return False


def cleanup_records(keys: list[str]) -> None:
    """Best-effort cleanup PR removing the listed records (XR + catalog files)."""
    paths = []
    for key in keys:
        xr_rel = xr_path(ZONE_NAME, key)
        cat_rel = catalog_path(ZONE_ENVIRONMENT, ZONE_NAME, key)
        if os.path.exists(os.path.join(REPO_ROOT, xr_rel)):
            paths.append(xr_rel)
        if os.path.exists(os.path.join(REPO_ROOT, cat_rel)):
            paths.append(cat_rel)
    if not paths:
        return
    branch = f"e2e-concurrency-cleanup-{int(time.time())}"
    try:
        run(["git", "-C", REPO_ROOT, "checkout", "-b", branch])
        run(["git", "-C", REPO_ROOT, "rm", *paths])
        run(["git", "-c", "user.name=Arthur Bryan", "-c",
             "user.email=arthurbryan2030@gmail.com", "-C", REPO_ROOT,
             "commit", "-m", f"chore(e2e-concurrency): cleanup {len(paths)} files"])
        run(["git", "-C", REPO_ROOT, "push", "-u", "origin", branch])
        pr_url = run([
            "gh", "pr", "create", "--base", GH_BRANCH, "--head", branch,
            "--title", "chore(e2e-concurrency): cleanup",
            "--body", "auto-cleanup from concurrency-scenarios test",
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


# ---------------------------------------------------------------------------
# Scenario 1: same record, two rapid edits — the later one must win.
# ---------------------------------------------------------------------------

def scenario_same_record_rapid_edits(suffix: str) -> bool:
    step(f"CONCURRENCY same-record-rapid-edits ({suffix})")
    record_name = f"e2e-conc-rapid-{suffix}"
    key = base_key(record_name, "A", None)
    xr_name = f"record-{key}.{ZONE_NAME}"
    fqdn = f"{record_name}.{ZONE_NAME}"

    info("creating baseline record (ttl=300, values=[10.0.40.10])")
    pr = submit_record_create(record_name, "A", {
        "ttl": 300, "values": ["10.0.40.10"], "routingPolicy": "simple",
    })
    if not pr or not merge_pr(pr):
        return False
    git_pull()
    if not argo_wait_revision("entities", git_pull(), 240):
        fail("argo did not sync create")
        return False
    if not wait_xr_ready(xr_name, 240):
        fail("create did not reach Ready")
        return False
    ok("baseline created")

    info("firing two edits within 1s: A=[10.0.40.20], B=[10.0.40.30]")
    edits = [
        ("A", {"ttl": 300, "values": ["10.0.40.20"]}),
        ("B", {"ttl": 300, "values": ["10.0.40.30"]}),
    ]
    prs: list[tuple[str, Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(submit_record_edit, record_name, "A", v): tag
                   for tag, v in edits}
        for fut in as_completed(futures):
            tag = futures[fut]
            try:
                prs.append((tag, fut.result()))
            except Exception as e:
                prs.append((tag, None))
                _p(f"  [fail] edit {tag} raised {e}")

    if any(p is None for _, p in prs):
        fail("at least one edit PR was not created")
        return False
    ok(f"both edits opened PRs: {[p for _, p in prs]}")

    # Merge sequentially; the later-merged one wins in git, which the platform
    # observes as the latest desired state.
    last_pr_tag, last_pr_url = prs[-1]
    info(f"merging in order: {[t for t, _ in prs]}")
    for tag, url in prs:
        if not merge_pr(url):
            fail(f"merge failed for edit {tag} ({url})")
            return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync edits")
        return False

    # Expected final state is whichever edit was last in the merge order.
    final_values = {"A": ["10.0.40.20"], "B": ["10.0.40.30"]}[last_pr_tag]
    info(f"last merged edit was '{last_pr_tag}', expected AWS values={final_values}")

    def converged() -> bool:
        rows = aws_records_at(fqdn)
        observed = sorted(r["Value"] for r in rows[0]["ResourceRecords"]) if rows else []
        return observed == sorted(final_values)

    if not wait_until(converged, deadline_s=300):
        fail(f"AWS did not converge to {final_values} within 5 min")
        return False
    ok(f"AWS converged to {final_values}")
    return True


# ---------------------------------------------------------------------------
# Scenario 2: weighted siblings updated in parallel — both bump TTL together
# so the AWS "siblings must have same TTL" constraint is satisfied.
# ---------------------------------------------------------------------------

def scenario_siblings_parallel_edit(suffix: str) -> bool:
    step(f"CONCURRENCY siblings-parallel-edit ({suffix})")
    base = f"e2e-conc-siblings-{suffix}"
    record_name = base
    fqdn = f"{base}.{ZONE_NAME}"

    # Create two weighted siblings sequentially (we test parallel EDIT, not
    # parallel CREATE, since CREATE has different invariants).
    siblings = [
        ("primary", 70, ["10.0.41.10"]),
        ("secondary", 30, ["10.0.41.20"]),
    ]
    for sid, weight, vals in siblings:
        info(f"creating sibling {sid}")
        pr = submit_record_create(record_name, "A", {
            "ttl": 300, "values": vals, "routingPolicy": "weighted",
            "setIdentifier": sid, "weight": weight,
        })
        if not pr or not merge_pr(pr):
            return False
    git_pull()
    if not argo_wait_revision("entities", git_pull(), 240):
        fail("argo did not sync create")
        return False
    for sid, _, _ in siblings:
        key = base_key(record_name, "A", sid)
        xr = f"record-{key}.{ZONE_NAME}"
        if not wait_xr_ready(xr, 240):
            fail(f"create did not reach Ready: {sid}")
            return False
    ok("both siblings created")

    # Parallel edits: bump TTL on both (300 -> 600) AND change values.
    info("firing parallel edits: TTL 300->600 and values rotated on both siblings")
    edits = [
        ("primary",   {"ttl": 600, "values": ["10.0.41.11"], "weight": 70,
                       "routingPolicy": "weighted"}),
        ("secondary", {"ttl": 600, "values": ["10.0.41.21"], "weight": 30,
                       "routingPolicy": "weighted"}),
    ]
    prs: list[tuple[str, Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(submit_record_edit, record_name, "A", v, sid): sid
                   for sid, v in edits}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                prs.append((sid, fut.result()))
            except Exception as e:
                prs.append((sid, None))
                _p(f"  [fail] edit {sid} raised {e}")
    if any(p is None for _, p in prs):
        fail("at least one sibling edit PR was not created")
        return False
    ok(f"both sibling edit PRs opened: {[p for _, p in prs]}")

    for sid, url in prs:
        if not merge_pr(url):
            fail(f"merge failed for sibling {sid}")
            return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync edits")
        return False

    expected = {"primary": ["10.0.41.11"], "secondary": ["10.0.41.21"]}

    def converged() -> bool:
        rows = aws_records_at(fqdn)
        if len(rows) < 2:
            return False
        observed = {}
        for r in rows:
            sid = r.get("SetIdentifier") or ""
            ttl = r.get("TTL")
            vals = sorted(rr["Value"] for rr in r["ResourceRecords"])
            observed[sid] = (ttl, vals)
        return all(
            observed.get(sid) == (600, sorted(expected[sid]))
            for sid in expected
        )

    if not wait_until(converged, deadline_s=420):
        rows = aws_records_at(fqdn)
        fail(f"siblings did not converge within 7 min. rows={rows}")
        return False
    ok("both siblings converged: ttl=600 with new values, set identifiers intact")
    return True


# ---------------------------------------------------------------------------
# Scenario 3: AWS "siblings must have same TTL" race. We change sibling-1's
# TTL first (which AWS rejects until sibling-2 matches), then a few seconds
# later change sibling-2's TTL too. Eventually both converge.
# ---------------------------------------------------------------------------

def scenario_sibling_ttl_race(suffix: str) -> bool:
    step(f"CONCURRENCY sibling-ttl-race ({suffix})")
    base = f"e2e-conc-ttlrace-{suffix}"
    fqdn = f"{base}.{ZONE_NAME}"

    siblings = [
        ("primary", 50, ["10.0.42.10"]),
        ("secondary", 50, ["10.0.42.20"]),
    ]
    for sid, weight, vals in siblings:
        info(f"creating sibling {sid}")
        pr = submit_record_create(base, "A", {
            "ttl": 300, "values": vals, "routingPolicy": "weighted",
            "setIdentifier": sid, "weight": weight,
        })
        if not pr or not merge_pr(pr):
            return False
    git_pull()
    if not argo_wait_revision("entities", git_pull(), 240):
        fail("argo did not sync create")
        return False
    for sid, _, _ in siblings:
        key = base_key(base, "A", sid)
        xr = f"record-{key}.{ZONE_NAME}"
        if not wait_xr_ready(xr, 240):
            fail(f"sibling {sid} did not reach Ready")
            return False
    ok("baseline siblings created at ttl=300")

    info("editing primary: ttl 300 -> 900 (expect rejection until secondary catches up)")
    primary_pr = submit_record_edit(base, "A", {
        "ttl": 900, "values": ["10.0.42.10"], "weight": 50,
        "routingPolicy": "weighted",
    }, set_identifier="primary")
    if not primary_pr or not merge_pr(primary_pr):
        return False

    info("waiting 30s so the platform tries (and AWS rejects) the primary edit")
    time.sleep(30)
    pri_mr = mr_status(f"record-{base_key(base, 'A', 'primary')}.{ZONE_NAME}")
    info(f"primary MR after 30s: synced={pri_mr.get('synced')} msg={(pri_mr.get('synced_msg') or '')[:120]}")

    info("editing secondary: ttl 300 -> 900 (this unblocks AWS)")
    secondary_pr = submit_record_edit(base, "A", {
        "ttl": 900, "values": ["10.0.42.20"], "weight": 50,
        "routingPolicy": "weighted",
    }, set_identifier="secondary")
    if not secondary_pr or not merge_pr(secondary_pr):
        return False
    head = git_pull()
    if not argo_wait_revision("entities", head, 240):
        fail("argo did not sync secondary edit")
        return False

    def converged() -> bool:
        rows = aws_records_at(fqdn)
        if len(rows) < 2:
            return False
        return all(r.get("TTL") == 900 for r in rows)

    if not wait_until(converged, deadline_s=420):
        rows = aws_records_at(fqdn)
        fail(f"siblings did not both reach ttl=900 within 7 min. rows={rows}")
        return False
    ok("both siblings converged at ttl=900")
    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, Callable[[str], bool]] = {
    "same-record-rapid-edits": scenario_same_record_rapid_edits,
    "siblings-parallel-edit":  scenario_siblings_parallel_edit,
    # sibling-ttl-race intentionally omitted: AWS Route 53's
    # "siblings must have same TTL" constraint applies at CREATE time, not at
    # UPDATE time, so changing one sibling's TTL while leaving the other alone
    # is accepted by AWS and not the failure mode we initially expected.
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", help="run only listed scenarios")
    ap.add_argument("--continue-on-fail", action="store_true")
    ap.add_argument("--suffix", default=time.strftime("%H%M%S"))
    ap.add_argument("--no-cleanup", action="store_true",
                    help="leave test records behind for inspection")
    args = ap.parse_args()

    names = args.only or list(SCENARIOS.keys())
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print(f"unknown scenarios: {unknown}", file=sys.stderr)
        return 2

    results: list[tuple[str, bool]] = []
    created_keys: list[str] = []
    for name in names:
        try:
            passed = SCENARIOS[name](args.suffix)
        except Exception as e:
            fail(f"scenario {name} raised: {type(e).__name__}: {e}")
            passed = False
        results.append((name, passed))
        # Track created XR keys for cleanup.
        if name == "same-record-rapid-edits":
            created_keys.append(base_key(f"e2e-conc-rapid-{args.suffix}", "A", None))
        elif name == "siblings-parallel-edit":
            for sid in ("primary", "secondary"):
                created_keys.append(base_key(f"e2e-conc-siblings-{args.suffix}", "A", sid))
        if not passed and not args.continue_on_fail:
            break

    if not args.no_cleanup and created_keys:
        info(f"cleaning up {len(created_keys)} test records …")
        cleanup_records(created_keys)

    print()
    print("=" * 60)
    print("SUMMARY")
    for name, passed in results:
        tag = "\033[0;32mPASS\033[0m" if passed else "\033[0;31mFAIL\033[0m"
        print(f"  {tag}  {name}")
    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
