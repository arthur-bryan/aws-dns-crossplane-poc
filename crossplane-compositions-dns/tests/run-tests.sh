#!/usr/bin/env bash
# Composition render tests.
#
# Runs `crossplane render` against each XR in xrs/ using the production
# composition + functions, and asserts invariants on the output.
#
# Requires: crossplane CLI (v2.x), Docker (for pulling function images),
#           helm (to render CRDs for dry-run validation), kubectl.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
XRS_DIR="$SCRIPT_DIR/xrs"
FUNCTIONS="$SCRIPT_DIR/functions.yaml"
OUT_DIR="$(mktemp -d -t dns-comp-tests-XXXXXX)"
trap "rm -rf $OUT_DIR" EXIT

pass=0
fail=0
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

render() {
  local xr="$1" comp="$2" out="$3"
  crossplane render "$xr" "$comp" "$FUNCTIONS" >"$out" 2>&1
}

assert_contains() {
  local file="$1" pattern="$2" label="$3"
  if grep -qE -e "$pattern" "$file"; then
    echo -e "  ${GREEN}✓${NC} $label"
    pass=$((pass+1))
  else
    echo -e "  ${RED}✗${NC} $label"
    echo -e "    ${YELLOW}expected pattern:${NC} $pattern"
    echo -e "    ${YELLOW}rendered output (first 30 lines):${NC}"
    head -30 "$file" | sed 's/^/      /'
    fail=$((fail+1))
  fi
}

assert_not_contains() {
  local file="$1" pattern="$2" label="$3"
  if ! grep -qE -e "$pattern" "$file"; then
    echo -e "  ${GREEN}✓${NC} $label"
    pass=$((pass+1))
  else
    echo -e "  ${RED}✗${NC} $label"
    echo -e "    ${YELLOW}unwanted pattern:${NC} $pattern"
    fail=$((fail+1))
  fi
}

# Helm-rendered composition files (resolves {{ .Values.managementPolicies }}).
HELM_RENDER="$OUT_DIR/helm.yaml"
helm template "$CHART_DIR" >"$HELM_RENDER"
# Extract individual composition docs into files crossplane render can use.
ZONE_COMP="$OUT_DIR/zone-composition.yaml"
RECORD_COMP="$OUT_DIR/record-composition.yaml"
awk '
  /^# Source: .*\/compositions\/zone\.yaml$/        { file = "ZONE"; next }
  /^# Source: .*\/compositions\/record\.yaml$/      { file = "RECORD"; next }
  /^# Source: .*\/crds\//                           { file = ""; next }
  file == "ZONE"   { print > "'"$ZONE_COMP"'" }
  file == "RECORD" { print > "'"$RECORD_COMP"'" }
' "$HELM_RENDER"

[ -s "$ZONE_COMP" ]   || { echo "ERROR: zone composition not extracted"; exit 1; }
[ -s "$RECORD_COMP" ] || { echo "ERROR: record composition not extracted"; exit 1; }

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

echo
echo "=== zone-create ==="
OUT="$OUT_DIR/zone-create.out"
render "$XRS_DIR/zone-create.yaml" "$ZONE_COMP" "$OUT"
assert_contains "$OUT" '^[[:space:]]+kind: Zone$' "Zone MR emitted"
assert_contains "$OUT" 'apiVersion: route53\.aws\.m\.upbound\.io/v1beta1' "Uses modern route53 API"
assert_not_contains "$OUT" 'crossplane\.io/external-name:' "external-name omitted on create (provider generates)"
assert_contains "$OUT" 'name: example\.com' "forProvider.name = example.com"
assert_contains "$OUT" 'comment: Corporate website DNS zone' "comment propagated"
assert_contains "$OUT" '- Create' "managementPolicies includes Create"
assert_contains "$OUT" '- Delete' "managementPolicies includes Delete"
assert_not_contains "$OUT" 'imported: "true"' "not tagged as imported"

echo
echo "=== zone-import (arthurbryan.com) ==="
OUT="$OUT_DIR/zone-import.out"
render "$XRS_DIR/zone-import.yaml" "$ZONE_COMP" "$OUT"
assert_contains "$OUT" 'crossplane\.io/external-name: Z03010981ALJFZB4QLU8W' "external-name = Zone ID"
assert_contains "$OUT" '- Observe' "managementPolicies includes Observe"
assert_contains "$OUT" '- Update' "managementPolicies includes Update"
assert_not_contains "$OUT" '- Create' "import does NOT include Create"
assert_not_contains "$OUT" '- Delete' "import does NOT include Delete"
assert_contains "$OUT" 'imported: "true"' "tagged as imported"
assert_contains "$OUT" 'name: arthurbryan\.com' "forProvider.name still set"

echo
echo "=== record-A with zoneId ==="
OUT="$OUT_DIR/record-a-with-zoneid.out"
render "$XRS_DIR/record-a-with-zoneid.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'kind: Record' "Record MR emitted"
assert_contains "$OUT" 'type: A' "type = A"
assert_contains "$OUT" 'zoneId: Z1234567890ABC' "zoneId propagated"
assert_contains "$OUT" 'ttl: 300' "ttl = 300"
assert_contains "$OUT" '192\.0\.2\.1' "value 192.0.2.1 present"
assert_not_contains "$OUT" 'crossplane\.io/external-name:' "external-name omitted on create"
assert_not_contains "$OUT" 'zone-lookup' "no zone-lookup path"

echo
echo "=== record-ALIAS (CloudFront) ==="
OUT="$OUT_DIR/record-alias-cf.out"
render "$XRS_DIR/record-alias-cloudfront.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'alias:' "alias block present"
assert_contains "$OUT" 'zoneId: Z2FDTNDATAQYW2' "CloudFront global hosted zone ID resolved"
assert_contains "$OUT" 'name: d1234567890abcd\.cloudfront\.net' "alias.name = dnsName"
assert_not_contains "$OUT" '^[[:space:]]+ttl:' "ALIAS has no ttl"
assert_not_contains "$OUT" '^[[:space:]]+records:' "ALIAS has no records"

echo
echo "=== record-ALIAS (ALB us-east-1) ==="
OUT="$OUT_DIR/record-alias-alb.out"
render "$XRS_DIR/record-alias-alb-us-east-1.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'zoneId: Z35SXDOTRQ7X7K' "ALB us-east-1 hosted zone ID resolved"
assert_contains "$OUT" 'evaluateTargetHealth: true' "evaluateTargetHealth propagated"

echo
echo "=== record-weighted ==="
OUT="$OUT_DIR/record-weighted.out"
render "$XRS_DIR/record-weighted.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'setIdentifier: blue-deployment' "setIdentifier propagated"
assert_contains "$OUT" 'weightedRoutingPolicy:' "weightedRoutingPolicy block present"
assert_contains "$OUT" 'weight: 70' "weight = 70"

echo
echo "=== record-import-A ==="
OUT="$OUT_DIR/record-import-a.out"
render "$XRS_DIR/record-import-a.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'crossplane\.io/external-name: Z1234567890ABC_legacy\.example\.com_A' "import external-name = zoneId_fqdn_type"
assert_contains "$OUT" '- Observe' "import has Observe"
assert_contains "$OUT" '- Update' "import has Update"
assert_not_contains "$OUT" '- Create' "import does NOT create"
assert_not_contains "$OUT" 'zone-lookup' "no zone-lookup when importing (zoneId provided)"

echo
echo "=== record-import-weighted-A ==="
OUT="$OUT_DIR/record-import-weighted.out"
render "$XRS_DIR/record-import-weighted-a.yaml" "$RECORD_COMP" "$OUT"
assert_contains "$OUT" 'crossplane\.io/external-name: Z1234567890ABC_api\.example\.com_A_green-deployment' \
  "import weighted external-name = zoneId_fqdn_type_setIdentifier"
assert_contains "$OUT" 'setIdentifier: green-deployment' "setIdentifier preserved on import"

# ---------------------------------------------------------------------------
# XRD validation tests — ensure CEL rules reject bad inputs.
# ---------------------------------------------------------------------------
echo
echo "=== XRD validation (kubectl dry-run against cluster) ==="
if kubectl get xrd zones.dock.tech >/dev/null 2>&1; then
  # Valid zone (should succeed)
  assert_contains <(kubectl apply --dry-run=server -f "$XRS_DIR/zone-create.yaml" 2>&1) \
    'created \(server dry run\)|configured \(server dry run\)' "valid zone passes dry-run"
  # Zone import without zoneId (should fail)
  INVALID_ZONE=$(mktemp)
  cat > "$INVALID_ZONE" <<'EOF'
apiVersion: dock.tech/v1
kind: Zone
metadata:
  name: bad-import
  namespace: system-infrastructure-dev
spec:
  name: bad-import
  domain: cross
  subdomain: cloud
  system: infrastructure
  environment: dev
  aws:
    account: 100000000000
    accountName: dev-account
  zoneName: example.com
  import:
    existing: true
EOF
  assert_contains <(kubectl apply --dry-run=server -f "$INVALID_ZONE" 2>&1) \
    'zoneId is required when spec\.import\.existing is true' "rejects import=true without zoneId"
  rm -f "$INVALID_ZONE"
else
  echo "  (skipped — XRD not installed in current cluster)"
fi

# ---------------------------------------------------------------------------
echo
echo "==============================="
echo -e "  ${GREEN}passed: $pass${NC}, ${RED}failed: $fail${NC}"
echo "==============================="
[ "$fail" -eq 0 ]
