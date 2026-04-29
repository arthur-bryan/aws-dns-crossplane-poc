BACKSTAGE_BACKEND="${BACKSTAGE_BACKEND:-http://localhost:7007}"

backstage_token() {
  curl -sf "$BACKSTAGE_BACKEND/api/auth/guest/refresh" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["backstageIdentity"]["token"])'
}

scaffolder_submit() {
  local template_ref="$1" values_json="$2"
  local token
  token=$(backstage_token)
  local payload
  payload=$(python3 -c "import json,sys; print(json.dumps({'templateRef': sys.argv[1], 'values': json.loads(sys.argv[2])}))" \
    "$template_ref" "$values_json")
  curl -sf -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$BACKSTAGE_BACKEND/api/scaffolder/v2/tasks" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

scaffolder_get_task() {
  local task_id="$1"
  local token
  token=$(backstage_token)
  curl -sf -H "Authorization: Bearer $token" \
    "$BACKSTAGE_BACKEND/api/scaffolder/v2/tasks/$task_id"
}

scaffolder_wait_task() {
  local task_id="$1" deadline="${2:-300}"
  local elapsed=0
  local interval=3
  local task_status
  while [ "$elapsed" -lt "$deadline" ]; do
    task_status=$(scaffolder_get_task "$task_id" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo unknown)
    case "$task_status" in
      completed|failed|cancelled)
        echo "$task_status"
        return 0
        ;;
    esac
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  echo "timeout"
  return 1
}

scaffolder_get_events() {
  local task_id="$1"
  local token
  token=$(backstage_token)
  curl -sf -H "Authorization: Bearer $token" \
    "$BACKSTAGE_BACKEND/api/scaffolder/v2/tasks/$task_id/events"
}

scaffolder_pr_url() {
  local task_id="$1"
  scaffolder_get_events "$task_id" \
    | python3 -c '
import json, sys
events = json.load(sys.stdin)
for e in events:
    if e.get("type") != "completion":
        continue
    output = (e.get("body") or {}).get("output") or {}
    for link in output.get("links") or []:
        if link.get("url"):
            print(link["url"])
            sys.exit(0)
    if output.get("remoteUrl"):
        print(output["remoteUrl"])
        sys.exit(0)
'
}

scaffolder_step_summary() {
  local task_id="$1"
  scaffolder_get_events "$task_id" \
    | python3 -c '
import json, sys
events = json.load(sys.stdin)
for e in events:
    typ = e.get("type")
    body = e.get("body") if isinstance(e.get("body"), dict) else {}
    msg = body.get("message")
    step = body.get("stepId") or "-"
    if msg:
        line = msg.strip().splitlines()[0][:140]
        print("  [" + typ + "] " + step + ": " + line)
'
}
