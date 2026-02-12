#!/bin/bash
# Import existing Route53 zone to GitOps YAML

set -e

ZONE_ID="$1"
ZONE_NAME="$2"
ENV="${3:-dev}"

if [ -z "$ZONE_ID" ] || [ -z "$ZONE_NAME" ]; then
  echo "Usage: $0 <zone-id> <zone-name> [environment]"
  echo ""
  echo "Examples:"
  echo "  $0 Z042057136AZ7P05F0XOW infradev.hml.dock.tech dev"
  echo "  $0 Z07088012G012PYYZ2302 infrahml.hml.dock.tech hml"
  exit 1
fi

OUTPUT_DIR="gitops/${ENV}"
OUTPUT_FILE="${OUTPUT_DIR}/${ZONE_NAME}.yaml"

mkdir -p "$OUTPUT_DIR"

if [ -f "$OUTPUT_FILE" ]; then
  echo "Error: Zone already exists: $OUTPUT_FILE"
  echo "Use sync-zone-records.sh to update existing zones"
  exit 1
fi

echo "Importing zone: $ZONE_NAME ($ZONE_ID)"
echo "Environment: $ENV"
echo ""

echo "Querying Route53..."
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" --output json > /tmp/route53-${ZONE_ID}.json

RECORD_COUNT=$(cat /tmp/route53-${ZONE_ID}.json | jq '[.ResourceRecordSets[] | select(.Type != "NS" and .Type != "SOA")] | length')
echo "Found $RECORD_COUNT records"
echo ""

cat > "$OUTPUT_FILE" << YAML_EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSZone
metadata:
  name: $(echo "$ZONE_NAME" | tr '.' '-')
  namespace: dns-system
  annotations:
    crossplane.io/external-name: "$ZONE_ID"
spec:
  zoneName: $ZONE_NAME
  environment: $ENV
  compositionRef:
    name: dnszones.aws.dns.crossplane.poc.observe
  tags:
    Account: $ENV
    Environment: $ENV
    ManagedBy: crossplane
    Team: infrastructure-services
    Tribe: cloud
  comment: Imported from Route53 (observe-only)

  records:
YAML_EOF

cat /tmp/route53-${ZONE_ID}.json | jq -r '
  .ResourceRecordSets[] |
  select(.Type != "NS" and .Type != "SOA") |

  (.Name | rtrimstr(".") | split(".") | .[0]) as $shortName |

  if .AliasTarget then
    "    - name: \"\($shortName)\"\n      type: \(.Type)\n      aliasTarget:\n        dnsName: \"\(.AliasTarget.DNSName)\"\n        hostedZoneId: \"\(.AliasTarget.HostedZoneId)\"\n        evaluateTargetHealth: \(.AliasTarget.EvaluateTargetHealth)"
  elif .SetIdentifier then
    "    - name: \"\($shortName)\"\n      type: \(.Type)\n      ttl: \(.TTL)\n      values:\n        - \"\(.ResourceRecords[0].Value)\"\n      setIdentifier: \"\(.SetIdentifier)\"\n      weight: \(.Weight // 0)"
  else
    "    - name: \"\($shortName)\"\n      type: \(.Type)\n      ttl: \(.TTL)\n      values:\n" + (.ResourceRecords | map("        - \"\(.Value)\"") | join("\n"))
  end
' >> "$OUTPUT_FILE"

rm -f /tmp/route53-${ZONE_ID}.json

echo "Created: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "  1. Review the generated YAML"
echo "  2. git add $OUTPUT_FILE"
echo "  3. git commit -m \"Import zone $ZONE_NAME from Route53\""
echo "  4. git push origin main"
echo "  5. ./scripts/operations/sync-gitops.sh $ENV"
