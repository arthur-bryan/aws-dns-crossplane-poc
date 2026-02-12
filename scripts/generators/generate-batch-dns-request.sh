#!/bin/bash
set -euo pipefail

COUNT=${1:-500}
OUTPUT=${2:-examples/dns-requests/batch-${COUNT}-records-generated.yaml}
ENV=${3:-dev}
ZONE=${4:-myapp.dev.dock.tech}
BUSINESS_UNIT=${5:-banking}

echo "[INFO] Generating DNSRequest with ${COUNT} records"
echo "[INFO] Output: ${OUTPUT}"

cat > "${OUTPUT}" <<EOF
apiVersion: dns.infra.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: req-batch-${COUNT}-records
  namespace: dns-system
  labels:
    env: ${ENV}
    action: create_record
    business-unit: ${BUSINESS_UNIT}
    batch: "true"
  annotations:
    crossplane.io/composition-resource-name: dnsrequests.batch.aws.cloudformation
spec:
  requesterName: batch.user@dock.tech
  requesterId: U99999999
  action: create_record
  env: ${ENV}
  hostedzone: ${ZONE}
  businessUnit: ${BUSINESS_UNIT}
  originTicket: https://jira.dock.tech/browse/BATCH-${COUNT}
  records:
EOF

for i in $(seq 1 $COUNT); do
  PADDED=$(printf "%04d" $i)
  IP_LAST_OCTET=$((($i - 1) % 254 + 1))
  IP_THIRD_OCTET=$((($i - 1) / 254 + 1))

  cat >> "${OUTPUT}" <<EOF
    - name: api-${PADDED}
      type: A
      value: "10.0.${IP_THIRD_OCTET}.${IP_LAST_OCTET}"
      ttl: "300"
EOF
done

echo "[INFO] Generated ${COUNT} records in ${OUTPUT}"
echo "[INFO] CloudFormation limit: 500 resources per stack"
if [ $COUNT -gt 500 ]; then
  echo "[WARN] Count exceeds CloudFormation limit. Consider splitting into multiple requests."
fi

echo "[INFO] Apply with: kubectl apply -f ${OUTPUT}"
