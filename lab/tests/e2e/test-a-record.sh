#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/ui.sh"
source "$SCRIPT_DIR/lib/scaffolder.sh"
source "$SCRIPT_DIR/lib/verify.sh"

require_cmds curl python3 kubectl aws git

ZONE_NAME="${ZONE_NAME:-arthurbryan.com}"
ZONE_ID="${ZONE_ID:-Z03010981ALJFZB4QLU8W}"
ZONE_REF="${ZONE_REF:-resource:system-infrastructure-dev/zone-${ZONE_NAME}}"
RECORD_KEY="${RECORD_KEY:-e2e-$(date +%H%M%S)}"
RECORD_TYPE="A"
INITIAL_VALUE="${INITIAL_VALUE:-192.0.2.10}"
INITIAL_TTL="${INITIAL_TTL:-300}"
UPDATED_VALUE="${UPDATED_VALUE:-192.0.2.20}"
UPDATED_TTL="${UPDATED_TTL:-600}"

XR_NAME=$(xr_name_for "$ZONE_NAME" "$RECORD_KEY")
FQDN="${RECORD_KEY}.${ZONE_NAME}"
XR_FILE=$(xr_path_for "$ZONE_NAME" "$RECORD_KEY")
CATALOG_FILE=$(catalog_path_for "$ZONE_NAME" "$RECORD_KEY")

info "zone:        $ZONE_NAME"
info "record:      $RECORD_KEY ($RECORD_TYPE)"
info "fqdn:        $FQDN"
info "xr name:     $XR_NAME"
info "initial:     $INITIAL_VALUE  ttl=$INITIAL_TTL"
info "update:      $UPDATED_VALUE  ttl=$UPDATED_TTL"

step "1/8  submit create task to Backstage scaffolder"
CREATE_VALUES=$(python3 -c "
import json, os
print(json.dumps({
    'zone':          os.environ['ZONE_REF'],
    'recordName':    os.environ['RECORD_KEY'],
    'type':          os.environ['RECORD_TYPE'],
    'ttl':           int(os.environ['INITIAL_TTL']),
    'values':        [os.environ['INITIAL_VALUE']],
    'routingPolicy': 'simple',
}))
" )
ZONE_REF="$ZONE_REF" RECORD_KEY="$RECORD_KEY" RECORD_TYPE="$RECORD_TYPE" \
  INITIAL_TTL="$INITIAL_TTL" INITIAL_VALUE="$INITIAL_VALUE"
CREATE_TASK=$(scaffolder_submit "template:default/aws-dns-record" "$CREATE_VALUES")
ok "task id: $CREATE_TASK"

step "2/8  wait for scaffolder to finish (writes XR + catalog YAML, opens PR)"
STATE=$(scaffolder_wait_task "$CREATE_TASK" 240) || true
if [ "$STATE" != "completed" ]; then
  fail "task ended with state=$STATE"
  scaffolder_step_summary "$CREATE_TASK"
  exit 1
fi
ok "task completed"

CREATE_PR_URL=$(scaffolder_pr_url "$CREATE_TASK")
if [ -z "$CREATE_PR_URL" ]; then
  fail "could not extract PR URL from task events"
  scaffolder_step_summary "$CREATE_TASK"
  exit 1
fi
ok "PR opened: $CREATE_PR_URL"

step "3/8  manual checkpoint — merge the create PR"
pause_for_merge "$CREATE_PR_URL"

step "4/8  pull main repo + verify entity files"
git_pull_repo
if [ -f "$XR_FILE" ]; then ok "XR file exists: ${XR_FILE#$REPO_ROOT/}"; else fail "missing $XR_FILE"; exit 1; fi
if [ -f "$CATALOG_FILE" ]; then ok "catalog file exists: ${CATALOG_FILE#$REPO_ROOT/}"; else fail "missing $CATALOG_FILE"; exit 1; fi

step "5/8  wait for Argo entities app to sync the merge commit"
TARGET_REV=$(git -C "$REPO_ROOT" rev-parse HEAD)
if wait_argo_revision entities "$TARGET_REV" 240; then
  ok "Argo entities app synced revision $TARGET_REV"
else
  fail "Argo did not pick up revision $TARGET_REV within 240s"
  exit 1
fi

step "6/8  wait for Crossplane to make the XR Synced+Ready"
if wait_xr_ready "$XR_NAME" 240; then
  ok "XR $XR_NAME is Synced + Ready"
else
  fail "XR did not reach Synced+Ready within 240s"
  kubectl -n "$NAMESPACE" describe "record.dock.tech/$XR_NAME" 2>&1 | tail -20 || true
  exit 1
fi

step "7/8  verify Route53 row matches the request"
RR_JSON=$(aws_record_value "$ZONE_ID" "$FQDN" "$RECORD_TYPE")
echo "  $RR_JSON"
GOT_TTL=$(printf '%s\n' "$RR_JSON"  | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d or [{}])[0].get("TTL","")) if d else print("")')
GOT_VAL=$(printf '%s\n' "$RR_JSON"  | python3 -c 'import json,sys; d=json.load(sys.stdin); v=(d or [{}])[0].get("Values",[]); print(",".join(v))')
if [ "$GOT_TTL" = "$INITIAL_TTL" ] && [ "$GOT_VAL" = "$INITIAL_VALUE" ]; then
  ok "Route53 has TTL=$GOT_TTL value=$GOT_VAL — matches request"
else
  fail "Route53 mismatch: expected TTL=$INITIAL_TTL value=$INITIAL_VALUE, got TTL=$GOT_TTL value=$GOT_VAL"
  exit 1
fi

step "8/8  CREATE phase passed"
ok "$FQDN $RECORD_TYPE => $INITIAL_VALUE (ttl $INITIAL_TTL)"

step "EDIT 1/4  submit edit task with new TTL + value"
EDIT_VALUES=$(python3 -c "
import json, os
print(json.dumps({
    'zone':       os.environ['ZONE_REF'],
    'recordName': os.environ['RECORD_KEY'],
    'type':       os.environ['RECORD_TYPE'],
    'ttl':        int(os.environ['UPDATED_TTL']),
    'values':     [os.environ['UPDATED_VALUE']],
}))
" )
RECORD_TYPE="$RECORD_TYPE" UPDATED_TTL="$UPDATED_TTL" UPDATED_VALUE="$UPDATED_VALUE"
EDIT_TASK=$(scaffolder_submit "template:default/aws-dns-record-edit" "$EDIT_VALUES")
ok "task id: $EDIT_TASK"

step "EDIT 2/4  wait for scaffolder to finish"
STATE=$(scaffolder_wait_task "$EDIT_TASK" 240) || true
if [ "$STATE" != "completed" ]; then
  fail "task ended with state=$STATE"
  scaffolder_step_summary "$EDIT_TASK"
  exit 1
fi
ok "task completed"

EDIT_PR_URL=$(scaffolder_pr_url "$EDIT_TASK")
if [ -z "$EDIT_PR_URL" ]; then
  fail "could not extract PR URL from task events"
  scaffolder_step_summary "$EDIT_TASK"
  exit 1
fi
ok "PR opened: $EDIT_PR_URL"

step "EDIT 3/4  manual checkpoint — merge the edit PR"
pause_for_merge "$EDIT_PR_URL"

step "EDIT 4/4  verify update propagates through git -> Argo -> XR -> AWS"
git_pull_repo
TARGET_REV=$(git -C "$REPO_ROOT" rev-parse HEAD)
wait_argo_revision entities "$TARGET_REV" 240 \
  && ok "Argo entities app synced revision $TARGET_REV" \
  || { fail "Argo did not pick up revision $TARGET_REV"; exit 1; }

wait_xr_ready "$XR_NAME" 240 \
  && ok "XR $XR_NAME is Synced + Ready (post-edit)" \
  || { fail "XR not Ready post-edit"; exit 1; }

XR_TTL=$(kubectl -n "$NAMESPACE" get "record.dock.tech/$XR_NAME" -o jsonpath='{.spec.ttl}')
XR_VALUES=$(kubectl -n "$NAMESPACE" get "record.dock.tech/$XR_NAME" -o jsonpath='{.spec.values[*]}')
[ "$XR_TTL" = "$UPDATED_TTL" ] \
  && ok "XR.spec.ttl = $XR_TTL" \
  || { fail "XR.spec.ttl=$XR_TTL (expected $UPDATED_TTL)"; exit 1; }
[ "$XR_VALUES" = "$UPDATED_VALUE" ] \
  && ok "XR.spec.values = $XR_VALUES" \
  || { fail "XR.spec.values=$XR_VALUES (expected $UPDATED_VALUE)"; exit 1; }

RR_JSON=$(aws_record_value "$ZONE_ID" "$FQDN" "$RECORD_TYPE")
GOT_TTL=$(printf '%s\n' "$RR_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d or [{}])[0].get("TTL","")) if d else print("")')
GOT_VAL=$(printf '%s\n' "$RR_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); v=(d or [{}])[0].get("Values",[]); print(",".join(v))')
if [ "$GOT_TTL" = "$UPDATED_TTL" ] && [ "$GOT_VAL" = "$UPDATED_VALUE" ]; then
  ok "Route53 reflects update: TTL=$GOT_TTL value=$GOT_VAL"
else
  fail "Route53 still showing TTL=$GOT_TTL value=$GOT_VAL (expected TTL=$UPDATED_TTL value=$UPDATED_VALUE)"
  exit 1
fi

step "DONE — A record create + update flow verified end-to-end"
ok "record FQDN: $FQDN"
ok "XR:         $XR_NAME"
ok "files:      ${XR_FILE#$REPO_ROOT/}"
ok "            ${CATALOG_FILE#$REPO_ROOT/}"
printf '\n'
printf '  %s\n' "$(yellow 'cleanup hint:')"
printf '    git rm "%s" "%s"\n' "${XR_FILE#$REPO_ROOT/}" "${CATALOG_FILE#$REPO_ROOT/}"
printf '    git commit -m "chore(e2e): remove %s test record" && open a delete PR\n' "$FQDN"
printf '    after merge, the AWS row will be removed by Crossplane\n'
