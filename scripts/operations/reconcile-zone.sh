#!/bin/bash
# Force reconciliation of Crossplane zone resources

set -e

ZONE_NAME="$1"

if [ -z "$ZONE_NAME" ]; then
  echo "Usage: $0 <zone-name>"
  echo ""
  echo "Examples:"
  echo "  $0 infradev-hml-dock-tech"
  echo "  $0 all  # Reconcile all zones"
  echo ""
  echo "Available zones:"
  kubectl get dnszone -n dns-system -o custom-columns=NAME:.metadata.name --no-headers 2>/dev/null || echo "  (none)"
  exit 1
fi

NAMESPACE="dns-system"

if [ "$ZONE_NAME" = "all" ]; then
  ZONES=$(kubectl get dnszone -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name --no-headers)
  
  echo "Reconciling all zones..."
  echo ""
  
  for zone in $ZONES; do
    echo "Zone: $zone"
    kubectl annotate dnszone "$zone" -n "$NAMESPACE" \
      reconcile.crossplane.io/force=$(date +%s) --overwrite
    echo "  Status: Reconciliation triggered"
  done
else
  echo "Reconciling zone: $ZONE_NAME"
  echo ""
  
  if ! kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE" > /dev/null 2>&1; then
    echo "Error: Zone not found: $ZONE_NAME"
    echo ""
    echo "Available zones:"
    kubectl get dnszone -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name --no-headers
    exit 1
  fi
  
  kubectl annotate dnszone "$ZONE_NAME" -n "$NAMESPACE" \
    reconcile.crossplane.io/force=$(date +%s) --overwrite
  echo "Status: Reconciliation triggered"
fi

echo ""
echo "Waiting for reconciliation (15s)..."
sleep 15

if [ "$ZONE_NAME" = "all" ]; then
  kubectl get dnszone -n "$NAMESPACE"
else
  kubectl get dnszone "$ZONE_NAME" -n "$NAMESPACE"
  echo ""
  kubectl describe dnszone "$ZONE_NAME" -n "$NAMESPACE" | tail -20
fi
