#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
XRS="$SCRIPT_DIR/xrs"
FUNCTIONS="$SCRIPT_DIR/functions.yaml"
WORK="$(mktemp -d -t dns-comp-tests-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0

red()    { printf '\033[0;31m%s\033[0m' "$1"; }
green()  { printf '\033[0;32m%s\033[0m' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m' "$1"; }
bold()   { printf '\033[1m%s\033[0m'   "$1"; }

require() {
  local missing=()
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'ERROR: missing required tools: %s\n' "${missing[*]}" >&2
    exit 1
  fi
}
require helm crossplane yq python3

HELM_OUT="$WORK/helm.yaml"
ZONE_COMP="$WORK/zone-composition.yaml"
RECORD_COMP="$WORK/record-composition.yaml"

helm template "$CHART_DIR" >"$HELM_OUT"
awk '
  /^# Source: .*\/compositions\/zone\.yaml$/   { f="ZONE";   next }
  /^# Source: .*\/compositions\/record\.yaml$/ { f="RECORD"; next }
  /^# Source: .*\/crds\//                      { f=""; next }
  f=="ZONE"   { print > "'"$ZONE_COMP"'" }
  f=="RECORD" { print > "'"$RECORD_COMP"'" }
' "$HELM_OUT"
[ -s "$ZONE_COMP" ]   || { echo "ERROR: zone composition empty"; exit 1; }
[ -s "$RECORD_COMP" ] || { echo "ERROR: record composition empty"; exit 1; }

ZONE_API="route53.aws.m.upbound.io/v1beta1"
RECORD_API="route53.aws.m.upbound.io/v1beta1"

render() {
  local xr="$1" comp="$2" out="$3"
  if ! crossplane render "$xr" "$comp" "$FUNCTIONS" >"$out" 2>"$out.err"; then
    return 1
  fi
}

doc_by_kind_api() {
  local file="$1" kind="$2" api="$3"
  yq eval-all "select(.kind == \"$kind\" and .apiVersion == \"$api\")" "$file"
}

pass_line() { printf '  %s %s\n' "$(green '[pass]')" "$1"; PASS=$((PASS+1)); }

fail_line() {
  local label="$1" expr="$2" want="$3" got="$4"
  printf '  %s %s\n' "$(red '[fail]')" "$label"
  printf '         expr     %s\n'   "$expr"
  printf '         expected %s\n'   "$(yellow "$want")"
  printf '         actual   %s\n'   "$(yellow "$got")"
  FAIL=$((FAIL+1))
}

assert_eq() {
  local doc="$1" path="$2" want="$3" label="$4"
  local got
  got=$(printf '%s\n' "$doc" | yq eval "$path" -)
  if [ "$got" = "$want" ]; then
    pass_line "$label"
  else
    fail_line "$label" "$path" "$want" "$got"
  fi
}

assert_null() {
  local doc="$1" path="$2" label="$3"
  assert_eq "$doc" "$path" "null" "$label"
}

assert_yq_true() {
  local doc="$1" expr="$2" label="$3"
  local got
  got=$(printf '%s\n' "$doc" | yq eval "$expr" -)
  if [ "$got" = "true" ]; then
    pass_line "$label"
  else
    fail_line "$label" "$expr" "true" "$got"
  fi
}

case_header() { printf '\n== %s ==\n' "$(bold "$1")"; }

render_record() {
  local label="$1" xr="$2" out="$3"
  if ! render "$xr" "$RECORD_COMP" "$out"; then
    printf '  %s render failed for %s\n' "$(red '[fail]')" "$xr"
    head -20 "$out.err" | sed 's/^/         /'
    FAIL=$((FAIL+1))
    return 1
  fi
}

render_zone() {
  local label="$1" xr="$2" out="$3"
  if ! render "$xr" "$ZONE_COMP" "$out"; then
    printf '  %s render failed for %s\n' "$(red '[fail]')" "$xr"
    head -20 "$out.err" | sed 's/^/         /'
    FAIL=$((FAIL+1))
    return 1
  fi
}

mr_record() { doc_by_kind_api "$1" "Record" "$RECORD_API"; }
mr_zone()   { doc_by_kind_api "$1" "Zone"   "$ZONE_API"; }

case_header "zone-create"
OUT="$WORK/zone-create.out"
if render_zone zone-create "$XRS/zone-create.yaml" "$OUT"; then
  doc=$(mr_zone "$OUT")
  assert_eq    "$doc" '.apiVersion'                           "$ZONE_API"               "apiVersion is modern v2"
  assert_eq    "$doc" '.spec.forProvider.name'                'example.com'             "forProvider.name = example.com"
  assert_eq    "$doc" '.spec.forProvider.comment'             'Corporate website DNS zone' "comment propagated"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Create"])' "managementPolicies includes Create"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Delete"])' "managementPolicies includes Delete"
  assert_null  "$doc" '.metadata.annotations["crossplane.io/external-name"]' "external-name omitted on create"
  assert_yq_true "$doc" '.spec.forProvider.tags == null or (.spec.forProvider.tags.imported == null)' "not tagged as imported"
  assert_null  "$doc" '.spec.forProvider.vpc' "public zone has no vpc block"
fi

case_header "zone-create-protected"
OUT="$WORK/zone-protected.out"
if render_zone zone-create-protected "$XRS/zone-create-protected.yaml" "$OUT"; then
  doc=$(mr_zone "$OUT")
  assert_eq "$doc" '.spec.deletionPolicy' 'Orphan' "deletionPolicy=Orphan emitted"
fi

case_header "zone-private"
OUT="$WORK/zone-private.out"
if render_zone zone-private "$XRS/zone-private.yaml" "$OUT"; then
  doc=$(mr_zone "$OUT")
  assert_eq      "$doc" '.spec.forProvider.vpc | length' '2'                "vpc block has two associations"
  assert_eq      "$doc" '.spec.forProvider.vpc[0].vpcId'        'vpc-0123456789abcdef0' "first vpcId propagated"
  assert_eq      "$doc" '.spec.forProvider.vpc[0].vpcRegion'    'us-east-1'             "first vpcRegion propagated"
  assert_eq      "$doc" '.spec.forProvider.vpc[1].vpcId'        'vpc-fedcba9876543210f' "second vpcId propagated"
  assert_eq      "$doc" '.spec.forProvider.tags.visibility'     'private'               "tag visibility=private set"
fi

case_header "zone-import"
OUT="$WORK/zone-import.out"
if render_zone zone-import "$XRS/zone-import.yaml" "$OUT"; then
  doc=$(mr_zone "$OUT")
  assert_eq      "$doc" '.metadata.annotations["crossplane.io/external-name"]' 'Z03010981ALJFZB4QLU8W' "external-name = Zone ID"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Observe"])' "managementPolicies includes Observe"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Update"])'  "managementPolicies includes Update"
  assert_yq_true "$doc" '.spec.managementPolicies | (contains(["Create"]) | not)'  "import does NOT include Create"
  assert_yq_true "$doc" '.spec.managementPolicies | (contains(["Delete"]) | not)'  "import does NOT include Delete"
  assert_eq      "$doc" '.spec.forProvider.tags.imported' 'true'         "tagged as imported"
  assert_eq      "$doc" '.spec.forProvider.name'          'arthurbryan.com' "forProvider.name still set"
fi

case_header "record-A with zoneId"
OUT="$WORK/record-a-with-zoneid.out"
if render_record record-a-with-zoneid "$XRS/record-a-with-zoneid.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type'   'A'                        "type = A"
  assert_eq      "$doc" '.spec.forProvider.zoneId' 'Z1234567890ABC'           "zoneId propagated"
  assert_eq      "$doc" '.spec.forProvider.ttl'    '300'                      "ttl = 300"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["192.0.2.1"])' "value 192.0.2.1 present"
  assert_eq      "$doc" '.metadata.annotations["crossplane.io/external-name"]' 'Z1234567890ABC_www.example.com_A' "external-name set deterministically on create"
  assert_null    "$doc" '.spec.forProvider.alias' "no alias block on simple record"
fi

case_header "record-AAAA"
OUT="$WORK/record-aaaa.out"
if render_record record-aaaa "$XRS/record-aaaa.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type'              'AAAA'         "type = AAAA"
  assert_eq      "$doc" '.spec.forProvider.ttl'               '3600'         "ttl preserved"
  assert_eq      "$doc" '.spec.forProvider.records | length'  '2'            "two values"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["2001:db8::1"])' "first IPv6 present"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["2001:db8::2"])' "second IPv6 present"
  assert_eq      "$doc" '.spec.forProvider.name' 'ipv6.example.com'           "FQDN built correctly"
fi

case_header "record-CNAME"
OUT="$WORK/record-cname.out"
if render_record record-cname "$XRS/record-cname.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type'             'CNAME'              "type = CNAME"
  assert_eq      "$doc" '.spec.forProvider.records | length' '1'                  "single value"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["app.example.com"])' "target propagated"
  assert_eq      "$doc" '.spec.forProvider.name'             'www.example.com'    "FQDN built correctly"
fi

case_header "record-NS subdomain delegation"
OUT="$WORK/record-ns.out"
if render_record record-ns "$XRS/record-ns.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type'             'NS'         "type = NS"
  assert_eq      "$doc" '.spec.forProvider.ttl'              '172800'     "high TTL preserved"
  assert_eq      "$doc" '.spec.forProvider.records | length' '4'          "four nameservers"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["ns1.example.com"])' "ns1 present"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["ns4.example.com"])' "ns4 present"
fi

case_header "record-PTR"
OUT="$WORK/record-ptr.out"
if render_record record-ptr "$XRS/record-ptr.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type' 'PTR'                          "type = PTR"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["server.example.com"])' "target propagated"
  assert_eq      "$doc" '.spec.forProvider.name' '1.0.168.192.in-addr.arpa'     "reverse-DNS FQDN built"
fi

case_header "record-CAA apex"
OUT="$WORK/record-caa.out"
if render_record record-caa "$XRS/record-caa.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type'             'CAA' "type = CAA"
  assert_eq      "$doc" '.spec.forProvider.records | length' '3'   "three CAA values"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["0 issue \"letsencrypt.org\""])' "letsencrypt issuer"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["0 issue \"amazon.com\""])'      "amazon issuer"
  assert_yq_true "$doc" '.spec.forProvider.records | any_c(test("iodef"))'                      "iodef value present"
  assert_eq      "$doc" '.spec.forProvider.name' '' "apex CAA has empty forProvider.name"
fi

case_header "record-ALIAS CloudFront (region-independent)"
OUT="$WORK/record-alias-cf.out"
if render_record record-alias-cloudfront "$XRS/record-alias-cloudfront.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq   "$doc" '.spec.forProvider.type'              'A'                            "ALIAS translated to A"
  assert_eq   "$doc" '.spec.forProvider.alias.zoneId'      'Z2FDTNDATAQYW2'               "CloudFront global hosted zone ID"
  assert_eq   "$doc" '.spec.forProvider.alias.name'        'd1234567890abcd.cloudfront.net' "alias.name = dnsName"
  assert_null "$doc" '.spec.forProvider.ttl'                                              "ALIAS has no ttl"
  assert_null "$doc" '.spec.forProvider.records'                                          "ALIAS has no records"
fi

case_header "record-ALIAS ALB us-east-1"
OUT="$WORK/record-alias-alb.out"
if render_record record-alias-alb "$XRS/record-alias-alb-us-east-1.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId'              'Z35SXDOTRQ7X7K' "ALB us-east-1 hosted zone"
  assert_eq "$doc" '.spec.forProvider.alias.evaluateTargetHealth' 'true'           "evaluateTargetHealth propagated"
fi

case_header "record-ALIAS ElasticBeanstalk us-west-2"
OUT="$WORK/record-alias-eb.out"
if render_record record-alias-eb "$XRS/record-alias-elasticbeanstalk.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId' 'Z38NKT9BP95V3O' "Elastic Beanstalk us-west-2 hosted zone"
fi

case_header "record-ALIAS NLB us-east-1"
OUT="$WORK/record-alias-nlb.out"
if render_record record-alias-nlb "$XRS/record-alias-nlb.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId'              'Z26RNL4JYFTOTI' "NLB us-east-1 hosted zone"
  assert_eq "$doc" '.spec.forProvider.alias.evaluateTargetHealth' 'true'           "evaluateTargetHealth propagated"
  assert_eq "$doc" '.spec.forProvider.type'                       'A'              "ALIAS translated to A"
fi

case_header "record-ALIAS S3Website us-east-1"
OUT="$WORK/record-alias-s3.out"
if render_record record-alias-s3 "$XRS/record-alias-s3website.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId' 'Z3AQBSTGFYJSTF'                       "S3 website us-east-1 hosted zone"
  assert_eq "$doc" '.spec.forProvider.alias.name'   'example.com.s3-website-us-east-1.amazonaws.com' "alias name preserved"
fi

case_header "record-ALIAS APIGateway us-east-1"
OUT="$WORK/record-alias-apigw.out"
if render_record record-alias-apigw "$XRS/record-alias-apigateway.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId' 'Z1UJRXOUMOOFQ8'                          "API Gateway us-east-1 hosted zone"
  assert_eq "$doc" '.spec.forProvider.alias.name'   'abcdef1234.execute-api.us-east-1.amazonaws.com' "alias name preserved"
fi

case_header "record-ALIAS GlobalAccelerator (region-independent)"
OUT="$WORK/record-alias-ga.out"
if render_record record-alias-ga "$XRS/record-alias-globalaccelerator.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId'              'Z2BJ6XQ5FK7U4H' "GA global hosted zone"
  assert_eq "$doc" '.spec.forProvider.alias.evaluateTargetHealth' 'true'           "evaluateTargetHealth propagated"
fi

case_header "record-ALIAS Custom (user-supplied hostedZoneId)"
OUT="$WORK/record-alias-custom.out"
if render_record record-alias-custom "$XRS/record-alias-custom.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.alias.zoneId' 'Z2FDTNDATAQYW2' "Custom uses user-provided hostedZoneId"
  assert_eq "$doc" '.spec.forProvider.alias.name'   'my-resource.us-east-1.example-service.amazonaws.com' "alias name preserved"
fi

case_header "record-ALIAS cross-region (DNS in us-east-1, ALB in eu-west-2)"
OUT="$WORK/record-alias-xregion.out"
if render_record record-alias-xregion "$XRS/record-alias-alb-cross-region.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.alias.zoneId' 'ZHURV8PSTC4K8' "aliasTarget.region (eu-west-2) wins over spec.aws.region"
  assert_yq_true "$doc" '.spec.forProvider.alias.zoneId != "Z35SXDOTRQ7X7K"' "us-east-1 ALB zoneId NOT used"
fi

case_header "record-weighted"
OUT="$WORK/record-weighted.out"
if render_record record-weighted "$XRS/record-weighted.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.setIdentifier'                   'blue-deployment' "setIdentifier propagated"
  assert_eq "$doc" '.spec.forProvider.weightedRoutingPolicy.weight'    '70'              "weight = 70"
fi

case_header "record-failover PRIMARY + health check"
OUT="$WORK/record-failover.out"
if render_record record-failover "$XRS/record-failover-primary.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq   "$doc" '.spec.forProvider.failoverRoutingPolicy.type' 'PRIMARY'                                  "failover type = PRIMARY"
  assert_eq   "$doc" '.spec.forProvider.healthCheckId'              '12345678-abcd-4abc-8abc-1234567890ab'    "healthCheckId propagated"
  assert_null "$doc" '.spec.forProvider.weightedRoutingPolicy'                                                "weighted NOT set"
fi

case_header "record-latency"
OUT="$WORK/record-latency.out"
if render_record record-latency "$XRS/record-latency.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.latencyRoutingPolicy.region' 'us-east-1' "latency.region = us-east-1"
fi

case_header "record-geolocation"
OUT="$WORK/record-geo.out"
if render_record record-geo "$XRS/record-geolocation.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.geolocationRoutingPolicy.continent' 'EU' "continent = EU"
fi

case_header "record-geoproximity awsRegion + bias"
OUT="$WORK/record-geoprox.out"
if render_record record-geoprox "$XRS/record-geoproximity.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.geoproximityRoutingPolicy.awsRegion' 'sa-east-1' "awsRegion propagated"
  assert_eq "$doc" '.spec.forProvider.geoproximityRoutingPolicy.bias'      '25'        "bias propagated"
fi

case_header "record-multivalue"
OUT="$WORK/record-mv.out"
if render_record record-multivalue "$XRS/record-multivalue.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.multivalueAnswerRoutingPolicy' 'true' "multivalueAnswerRoutingPolicy = true"
  assert_yq_true "$doc" '.spec.forProvider.healthCheckId != null'                "healthCheckId set on multivalue"
fi

case_header "record-import-A"
OUT="$WORK/record-import-a.out"
if render_record record-import-a "$XRS/record-import-a.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.metadata.annotations["crossplane.io/external-name"]' 'Z1234567890ABC_legacy.example.com_A' "import external-name = zoneId_fqdn_type"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Observe"])' "import has Observe"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Update"])'  "import has Update"
  assert_yq_true "$doc" '.spec.managementPolicies | (contains(["Create"]) | not)'  "import does NOT create"
fi

case_header "record-import-weighted-A"
OUT="$WORK/record-import-weighted.out"
if render_record record-import-weighted "$XRS/record-import-weighted-a.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.metadata.annotations["crossplane.io/external-name"]' 'Z1234567890ABC_api.example.com_A_green-deployment' "weighted external-name = zoneId_fqdn_type_setIdentifier"
  assert_eq "$doc" '.spec.forProvider.setIdentifier'                       'green-deployment'                                  "setIdentifier preserved on import"
fi

case_header "record-MX apex multi-value"
OUT="$WORK/record-mx-apex.out"
if render_record record-mx-apex "$XRS/record-mx-apex.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type' 'MX' "type = MX"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["10 mail1.example.com"])' "first MX value present"
  assert_yq_true "$doc" '.spec.forProvider.records | contains(["20 mail2.example.com"])' "second MX value present"
  assert_eq      "$doc" '.spec.forProvider.name' '' "apex MX has empty forProvider.name"
fi

case_header "record-SRV"
OUT="$WORK/record-srv.out"
if render_record record-srv "$XRS/record-srv.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.spec.forProvider.type' 'SRV' "type = SRV"
  assert_yq_true "$doc" '.spec.forProvider.records | any_c(test("10 60 5060 sipserver1"))' "SRV value parts preserved"
fi

case_header "record-apex-alias (empty recordName)"
OUT="$WORK/record-apex-alias.out"
if render_record record-apex-alias "$XRS/record-apex-alias.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq "$doc" '.spec.forProvider.type'         'A'                "ALIAS translated to A"
  assert_eq "$doc" '.spec.forProvider.alias.zoneId' 'Z2FDTNDATAQYW2'   "CloudFront hosted zone resolved"
  assert_eq "$doc" '.spec.forProvider.name'         ''                 "apex has empty forProvider.name"
fi

case_header "record-apex-import-txt (double-underscore external-name)"
OUT="$WORK/record-apex-import-txt.out"
if render_record record-apex-import-txt "$XRS/record-apex-import-txt.yaml" "$OUT"; then
  doc=$(mr_record "$OUT")
  assert_eq      "$doc" '.metadata.annotations["crossplane.io/external-name"]' 'Z1234567890ABC__TXT' "apex import external-name is zoneId__type"
  assert_eq      "$doc" '.spec.forProvider.name'                                ''                  "apex has empty forProvider.name"
  assert_yq_true "$doc" '.spec.managementPolicies | contains(["Observe"])'                            "import still observe+update"
fi

case_header "XRD validation (server dry-run)"
if kubectl get xrd zones.dock.tech >/dev/null 2>&1; then
  if kubectl apply --dry-run=server -f "$XRS/zone-create.yaml" >"$WORK/dryrun.out" 2>&1 \
     && grep -qE 'created \(server dry run\)|configured \(server dry run\)' "$WORK/dryrun.out"; then
    pass_line "valid zone passes dry-run"
  else
    fail_line "valid zone passes dry-run" "kubectl apply --dry-run=server" "created/configured" "$(head -2 "$WORK/dryrun.out")"
  fi
  cat > "$WORK/invalid-zone.yaml" <<'EOF'
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
  if kubectl apply --dry-run=server -f "$WORK/invalid-zone.yaml" >"$WORK/dryrun.err" 2>&1; then
    fail_line "rejects import=true without zoneId" "CEL rule" "rejection" "accepted (no rejection)"
  else
    if grep -q 'zoneId is required when spec.import.existing is true' "$WORK/dryrun.err"; then
      pass_line "rejects import=true without zoneId"
    else
      fail_line "rejects import=true without zoneId" "CEL message" "zoneId required" "$(head -2 "$WORK/dryrun.err")"
    fi
  fi
else
  printf '  %s XRD not installed in current cluster\n' "$(yellow '[skip]')"
fi

case_header "edit-template round-trip (data-model losslessness)"
ROUNDTRIP_OUT="$WORK/roundtrip.out"
if python3 "$SCRIPT_DIR/edit-roundtrip.py" \
     --xrs-dir "$XRS" \
     --record-composition "$RECORD_COMP" \
     --functions "$FUNCTIONS" \
     --work-dir "$WORK/roundtrip" \
     >"$ROUNDTRIP_OUT" 2>&1; then
  pass_count=$(grep -c '^\[pass\]' "$ROUNDTRIP_OUT" || true)
  fail_count=$(grep -c '^\[fail\]' "$ROUNDTRIP_OUT" || true)
  if [ "$fail_count" -gt 0 ]; then
    cat "$ROUNDTRIP_OUT" | sed 's/^/  /'
    FAIL=$((FAIL + fail_count))
  else
    cat "$ROUNDTRIP_OUT" | sed 's/^/  /'
    PASS=$((PASS + pass_count))
  fi
else
  printf '  %s round-trip script failed\n' "$(red '[fail]')"
  cat "$ROUNDTRIP_OUT" | sed 's/^/         /'
  FAIL=$((FAIL+1))
fi

echo
echo "==============================="
printf '  %s  %s\n' "$(green "passed: $PASS")" "$(red "failed: $FAIL")"
echo "==============================="
[ "$FAIL" -eq 0 ]
