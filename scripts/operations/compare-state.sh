#!/bin/bash
# Compare GitOps YAML with cluster state

set -e

ZONE_FILE="$1"

if [ -z "$ZONE_FILE" ]; then
  echo "Usage: $0 <zone-yaml-file>"
  echo ""
  echo "Examples:"
  echo "  $0 gitops/dev/infradev.hml.dock.tech.yaml"
  exit 1
fi

if [ ! -f "$ZONE_FILE" ]; then
  echo "Error: File not found: $ZONE_FILE"
  exit 1
fi

ZONE_NAME=$(yq eval '.metadata.name' "$ZONE_FILE")
NAMESPACE=$(yq eval '.metadata.namespace' "$ZONE_FILE")

echo "Comparing state for: $ZONE_NAME"
echo ""

if ! kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE" > /dev/null 2>&1; then
  echo "Status: Zone not in cluster"
  echo "Action: Apply with sync-gitops.sh"
  exit 0
fi

echo "Git version:"
yq eval '.spec.zoneName' "$ZONE_FILE"
GIT_RECORDS=$(yq eval '.spec.records | length' "$ZONE_FILE")
echo "Records: $GIT_RECORDS"
echo ""

echo "Cluster version:"
kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.zoneName}'
echo ""
CLUSTER_RECORDS=$(kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE" -o json | jq '.spec.records | length')
echo "Records: $CLUSTER_RECORDS"
echo ""

if [ "$GIT_RECORDS" != "$CLUSTER_RECORDS" ]; then
  echo "Status: DRIFT DETECTED"
  echo "Git has $GIT_RECORDS records, cluster has $CLUSTER_RECORDS records"
  echo ""
  echo "Action: Run sync-gitops.sh to apply changes"
else
  echo "Status: IN SYNC"
  echo ""
  
  echo "Zone status:"
  kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE"
fi
