#!/bin/bash
# Automatically sync Route53 records to GitOps YAML with drift detection

set -e

ZONE_NAME="$1"
ENV="${2:-dev}"

if [ -z "$ZONE_NAME" ]; then
  echo "Usage: $0 <zone-name> [env]"
  echo ""
  echo "Examples:"
  echo "  $0 infradev.hml.dock.tech"
  echo "  $0 infradev.hml.dock.tech dev"
  echo "  $0 infrahml.hml.dock.tech hml"
  echo ""
  echo "This script will:"
  echo "  1. Query Route53 for all records in the zone"
  echo "  2. Compare with current GitOps YAML"
  echo "  3. Show drift (added/deleted records)"
  echo "  4. Update the YAML file with current Route53 state"
  exit 1
fi

YAML_FILE="gitops/${ENV}/${ZONE_NAME}.yaml"

echo "Syncing zone: $ZONE_NAME (env: $ENV)"
echo ""

if [ ! -f "$YAML_FILE" ]; then
  echo "Error: GitOps YAML not found: $YAML_FILE"
  echo "Create the zone first or check the file path"
  exit 1
fi

ZONE_ID=$(grep 'crossplane.io/external-name:' "$YAML_FILE" | awk '{print $2}' | tr -d '"')

if [ -z "$ZONE_ID" ]; then
  echo "Error: Could not extract zone ID from $YAML_FILE"
  echo "Make sure the file has: crossplane.io/external-name annotation"
  exit 1
fi

echo "Found zone ID: $ZONE_ID"
echo ""

echo "Querying Route53 for current records..."
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" --output json > /tmp/route53-records-${ZONE_ID}.json

ROUTE53_COUNT=$(cat /tmp/route53-records-${ZONE_ID}.json | jq '[.ResourceRecordSets[] | select(.Type != "NS" and .Type != "SOA")] | length')
echo "Found $ROUTE53_COUNT records in Route53"
echo ""

YAML_COUNT=$(grep -c "^    - name:" "$YAML_FILE" || echo "0")
echo "Current GitOps YAML has $YAML_COUNT records"
echo ""

DRIFT=$((ROUTE53_COUNT - YAML_COUNT))
if [ $DRIFT -gt 0 ]; then
  echo "DRIFT DETECTED: +$DRIFT records added in Route53"
elif [ $DRIFT -lt 0 ]; then
  echo "DRIFT DETECTED: $DRIFT records deleted from Route53"
else
  echo "No drift detected (same record count)"
fi
echo ""

BACKUP_FILE="${YAML_FILE}.backup-$(date +%Y%m%d-%H%M%S)"
cp "$YAML_FILE" "$BACKUP_FILE"
echo "Backed up current YAML to: $BACKUP_FILE"
echo ""

sed -n '1,/^  records:/p' "$YAML_FILE" | head -n -1 > /tmp/yaml-header-${ZONE_ID}.yaml

echo "Generating new records section from Route53..."

cat > /tmp/yaml-records-${ZONE_ID}.yaml << 'INNER_EOF'
  records:
INNER_EOF

cat /tmp/route53-records-${ZONE_ID}.json | jq -r '
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
' >> /tmp/yaml-records-${ZONE_ID}.yaml

cat /tmp/yaml-header-${ZONE_ID}.yaml > "$YAML_FILE"
cat /tmp/yaml-records-${ZONE_ID}.yaml >> "$YAML_FILE"

echo "Updated $YAML_FILE with current Route53 state"
echo ""

echo "Drift report:"
echo ""
git diff --no-index --color=always "$BACKUP_FILE" "$YAML_FILE" || true
echo ""

echo "=================================================="
echo "Next steps:"
echo ""
echo "1. Review changes above"
echo "2. If correct, commit to Git:"
echo ""
echo "   git add $YAML_FILE"
echo "   git commit -m \"Sync Route53 records for $ZONE_NAME (+$DRIFT drift)\""
echo "   git push origin main"
echo ""
echo "3. If incorrect, restore backup:"
echo ""
echo "   mv $BACKUP_FILE $YAML_FILE"
echo ""
echo "Backup saved at: $BACKUP_FILE"
