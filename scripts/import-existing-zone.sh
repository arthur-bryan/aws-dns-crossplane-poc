#!/bin/bash
set -euo pipefail

ZONE_NAME="${1:-}"
ENVIRONMENT="${2:-dev}"
DOMAIN="${3:-cross}"
SUBDOMAIN="${4:-cloud}"
SYSTEM="${5:-imported}"
AWS_PROFILE="${AWS_PROFILE:-default}"

if [[ -z "$ZONE_NAME" ]]; then
  echo "Usage: $0 <zone-name> [environment] [domain] [subdomain] [system]"
  echo "Example: $0 example.com dev cross cloud myapp"
  exit 1
fi

ZONE_ID=$(aws route53 list-hosted-zones-by-name \
  --dns-name "$ZONE_NAME" \
  --profile "$AWS_PROFILE" \
  --query "HostedZones[?Name=='${ZONE_NAME}.'].Id" \
  --output text | sed 's|/hostedzone/||')

if [[ -z "$ZONE_ID" ]]; then
  echo "Error: Zone $ZONE_NAME not found in Route53"
  exit 1
fi

echo "Found zone: $ZONE_NAME (ID: $ZONE_ID)"

AWS_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
AWS_REGION=$(aws configure get region --profile "$AWS_PROFILE" || echo "us-east-2")

RECORDS=$(aws route53 list-resource-record-sets \
  --hosted-zone-id "$ZONE_ID" \
  --profile "$AWS_PROFILE" \
  --output json)

YAML_FILE="${ZONE_NAME//./-}-import.yaml"

cat > "$YAML_FILE" <<EOF
apiVersion: dock.tech/v1
kind: DNSZone
metadata:
  name: $(echo "$ZONE_NAME" | sed 's/\./-/g')
  namespace: ${DOMAIN}-${SUBDOMAIN}-${SYSTEM}
  annotations:
    crossplane.io/composition-name: dnszone-import
spec:
  domain: $DOMAIN
  subdomain: $SUBDOMAIN
  system: $SYSTEM
  environment: $ENVIRONMENT
  aws:
    account: $AWS_ACCOUNT
    accountName: ${ENVIRONMENT}-account
    region: $AWS_REGION
  zoneName: $ZONE_NAME
  records:
EOF

echo "$RECORDS" | jq -r '.ResourceRecordSets[] |
  select(.Type != "NS" and .Type != "SOA") |
  "    - name: \(.Name | rtrimstr(".'$ZONE_NAME'.") | rtrimstr("."))\n      type: \(.Type)\n      ttl: \(.TTL // 300)\n      values:\n\(.ResourceRecords // [] | map("        - \"\(.Value)\"") | join("\n"))\(if .SetIdentifier then "\n      setIdentifier: \(.SetIdentifier)" else "" end)\(if .Weight then "\n      weight: \(.Weight)" else "" end)"' >> "$YAML_FILE"

echo ""
echo "Generated: $YAML_FILE"
echo ""
echo "Next steps:"
echo "1. Review the generated YAML file"
echo "2. Apply to cluster: kubectl apply -f $YAML_FILE"
echo "3. Verify: kubectl get dnszone $(echo "$ZONE_NAME" | sed 's/\./-/g') -n ${DOMAIN}-${SUBDOMAIN}-${SYSTEM}"
echo "4. Check status: kubectl describe dnszone $(echo "$ZONE_NAME" | sed 's/\./-/g') -n ${DOMAIN}-${SUBDOMAIN}-${SYSTEM}"
