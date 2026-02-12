#!/bin/bash
# Sync Route53 records to GitOps YAML (for observe mode import)

ZONE_ID="$1"
ZONE_NAME="$2"
ENV="$3"
OUTPUT_FILE="gitops/${ENV}/${ZONE_NAME}.yaml"

if [ -z "$ZONE_ID" ] || [ -z "$ZONE_NAME" ] || [ -z "$ENV" ]; then
  echo "Usage: $0 <zone-id> <zone-name> <env>"
  echo "Example: $0 Z042057136AZ7P05F0XOW infradev.hml.dock.tech dev"
  exit 1
fi

echo "Fetching records from Route53 zone $ZONE_ID..."

# Query Route53 for all records
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --output json > /tmp/route53-records.json

# Parse records and generate YAML (you'd implement actual parsing here)
# For now, just show what's in Route53
echo ""
echo "Records found in Route53:"
cat /tmp/route53-records.json | jq -r '.ResourceRecordSets[] | 
  select(.Type != "NS" and .Type != "SOA") | 
  "  - name: \"\(.Name | rtrimstr(".'$ZONE_NAME'.") | rtrimstr("."))\"\n    type: \(.Type)\n    ttl: \(.TTL // 300)\n    values:\n      - \"\(.ResourceRecords[0].Value)\""'

echo ""
echo "Next steps:"
echo "1. Copy the records above to $OUTPUT_FILE"
echo "2. git add $OUTPUT_FILE"
echo "3. git commit -m 'Sync records from Route53 for $ZONE_NAME'"
echo "4. git push origin main"
