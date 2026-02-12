#!/bin/bash
set -euo pipefail

# Usage: ./generate-zone-with-batch-records.sh create 50 [zone-name] [env] [zone-id]
#        ./generate-zone-with-batch-records.sh delete 50 [zone-name] [env]

ACTION=${1:-create}
RECORD_COUNT=${2:-50}
ZONE_NAME=${3:-arthurbryan.dev.br}
ENV=${4:-poc}
ZONE_ID=${5:-}  # Optional: for importing existing zone

if [[ ! "$ACTION" =~ ^(create|delete)$ ]]; then
  echo "[ERROR] Action must be 'create' or 'delete'"
  echo "Usage: $0 <create|delete> <count> [zone-name] [env] [zone-id]"
  exit 1
fi

OUTPUT="examples/dnszones/zone-${ACTION}-${RECORD_COUNT}-records.yaml"

echo "[INFO] Action: ${ACTION}"
echo "[INFO] Generating DNSZone with ${RECORD_COUNT} records"
echo "[INFO] Zone: ${ZONE_NAME}"
echo "[INFO] Output: ${OUTPUT}"

if [ "$ACTION" = "create" ]; then
  # CREATE MODE: Generate zone with test records
  cat > "${OUTPUT}" <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSZone
metadata:
  name: zone-$(echo ${ZONE_NAME} | tr '.' '-')-batch-test
  annotations:
EOF

  # Add external-name annotation if zone ID provided (import mode)
  if [ -n "${ZONE_ID}" ]; then
    echo "[INFO] Import mode: Zone ID ${ZONE_ID}"
    cat >> "${OUTPUT}" <<EOF
    # Import existing zone
    crossplane.io/external-name: ${ZONE_ID}
EOF
  else
    echo "[INFO] Create mode: New zone will be created"
  fi

  cat >> "${OUTPUT}" <<EOF
spec:
  zoneName: ${ZONE_NAME}
  environment: ${ENV}
  comment: "Zone with ${RECORD_COUNT} test records for batch testing"
  compositionRef:
    name: dnszones.batch.cloudformation
  tags:
    ManagedBy: Crossplane
    GitOps: "true"
    RecordCount: "${RECORD_COUNT}"

  # All records created in ONE CloudFormation batch API call
  records:
EOF

  for i in $(seq 1 $RECORD_COUNT); do
    PADDED=$(printf "%04d" $i)
    IP_LAST_OCTET=$((($i - 1) % 254 + 1))
    IP_THIRD_OCTET=$((($i - 1) / 254 + 1))

    cat >> "${OUTPUT}" <<EOF
    - name: test-batch-${PADDED}
      type: A
      ttl: 300
      values:
        - "10.99.${IP_THIRD_OCTET}.${IP_LAST_OCTET}"
EOF
  done

elif [ "$ACTION" = "delete" ]; then
  # DELETE MODE: Generate zone WITHOUT test records (empty records array)
  cat > "${OUTPUT}" <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSZone
metadata:
  name: zone-$(echo ${ZONE_NAME} | tr '.' '-')-batch-test
  annotations:
EOF

  if [ -n "${ZONE_ID}" ]; then
    cat >> "${OUTPUT}" <<EOF
    # Import existing zone
    crossplane.io/external-name: ${ZONE_ID}
EOF
  fi

  cat >> "${OUTPUT}" <<EOF
spec:
  zoneName: ${ZONE_NAME}
  environment: ${ENV}
  comment: "Deleting ${RECORD_COUNT} test records via CloudFormation batch"
  compositionRef:
    name: dnszones.batch.cloudformation
  tags:
    ManagedBy: Crossplane
    GitOps: "true"

  # Empty records array - CloudFormation will DELETE all test records
  records: []
EOF
fi

echo ""
echo "[INFO] Generated manifest: ${OUTPUT}"
echo ""

if [ "$ACTION" = "create" ]; then
  echo "[INFO] CloudFormation limit: 500 resources per stack"
  if [ $RECORD_COUNT -gt 500 ]; then
    echo "[WARN] Count exceeds CloudFormation limit. Split into multiple zones or reduce records."
  fi

  echo ""
  echo "[INFO] To CREATE ${RECORD_COUNT} test records:"
  echo "  kubectl apply -f ${OUTPUT}"
  echo ""
  echo "[INFO] Performance comparison:"
  echo "  - Traditional: ${RECORD_COUNT} API calls (~$(( RECORD_COUNT / 5 )) seconds with rate limiting)"
  echo "  - Batch (CFN): 1 API call (~30-60 seconds CloudFormation processing)"
  echo ""
  echo "[INFO] Monitor stack creation:"
  echo "  kubectl get stacks -n crossplane-system -w"
  echo "  kubectl get dnszone zone-$(echo ${ZONE_NAME} | tr '.' '-')-batch-test -n dns-system -w"

elif [ "$ACTION" = "delete" ]; then
  echo "[INFO] To DELETE ${RECORD_COUNT} test records:"
  echo "  kubectl apply -f ${OUTPUT}"
  echo ""
  echo "[INFO] CloudFormation will delete the entire stack in 1 batch operation"
  echo ""
  echo "[INFO] Monitor stack deletion:"
  echo "  kubectl get stacks -n crossplane-system -w"
  echo ""
  echo "[INFO] Or delete the entire zone:"
  echo "  kubectl delete dnszone zone-$(echo ${ZONE_NAME} | tr '.' '-')-batch-test -n dns-system"
fi
