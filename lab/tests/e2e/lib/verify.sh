REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
NAMESPACE="${NAMESPACE:-system-infrastructure-dev}"

aws_with_creds() {
  local creds key secret
  creds=$(kubectl -n crossplane-system get secret aws-creds -o jsonpath='{.data.credentials}' | base64 -d)
  key=$(printf '%s\n' "$creds" | grep aws_access_key_id     | awk -F'= ' '{print $2}' | tr -d '[:space:]')
  secret=$(printf '%s\n' "$creds" | grep aws_secret_access_key | awk -F'= ' '{print $2}' | tr -d '[:space:]')
  AWS_ACCESS_KEY_ID="$key" AWS_SECRET_ACCESS_KEY="$secret" AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" aws "$@"
}

git_pull_repo() {
  git -C "$REPO_ROOT" fetch --quiet origin
  git -C "$REPO_ROOT" pull --ff-only --quiet
}

xr_path_for() {
  local zone_name="$1" record_key="$2"
  echo "$REPO_ROOT/ape-platform-entities/environments/cross/cloud/infrastructure/dev/resources/aws/$zone_name/record-$record_key.yaml"
}

catalog_path_for() {
  local zone_name="$1" record_key="$2"
  echo "$REPO_ROOT/ape-platform-entities/catalog/dev/$zone_name/record-$record_key.yaml"
}

xr_name_for() {
  local zone_name="$1" record_key="$2"
  echo "record-$record_key.$zone_name"
}

wait_argo_revision() {
  local app="$1" revision="$2" deadline="${3:-180}"
  local elapsed=0
  while [ "$elapsed" -lt "$deadline" ]; do
    kubectl -n argocd patch "application/$app" --type merge \
      -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' >/dev/null 2>&1 || true
    local got
    got=$(kubectl -n argocd get "application/$app" -o jsonpath='{.status.sync.revision}' 2>/dev/null || echo)
    if [ "$got" = "$revision" ]; then
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  return 1
}

wait_xr_ready() {
  local xr_name="$1" deadline="${2:-180}"
  local elapsed=0
  while [ "$elapsed" -lt "$deadline" ]; do
    local synced ready
    synced=$(kubectl -n "$NAMESPACE" get "record.dock.tech/$xr_name" \
      -o jsonpath='{.status.conditions[?(@.type=="Synced")].status}' 2>/dev/null || echo)
    ready=$(kubectl -n "$NAMESPACE" get "record.dock.tech/$xr_name" \
      -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'  2>/dev/null || echo)
    if [ "$synced" = "True" ] && [ "$ready" = "True" ]; then
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  return 1
}

aws_record_value() {
  local zone_id="$1" fqdn="$2" rtype="$3"
  aws_with_creds route53 list-resource-record-sets \
    --hosted-zone-id "$zone_id" \
    --query "ResourceRecordSets[?Name=='${fqdn}.' && Type=='$rtype'].{TTL:TTL,Values:ResourceRecords[].Value}" \
    --output json
}
