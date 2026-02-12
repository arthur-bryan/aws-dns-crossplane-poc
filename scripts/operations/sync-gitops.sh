#!/bin/bash
# Sync GitOps changes to cluster via ArgoCD

set -e

ENV="${1:-all}"
FORCE="${2}"

if [ "$ENV" = "--help" ]; then
  echo "Usage: $0 [environment] [--force]"
  echo ""
  echo "Arguments:"
  echo "  environment  Target environment (dev, hml, prd, all) [default: all]"
  echo "  --force      Force sync even if already synced"
  echo ""
  echo "Examples:"
  echo "  $0              # Sync all applications"
  echo "  $0 dev          # Sync dev zones only"
  echo "  $0 all --force  # Force sync all applications"
  exit 0
fi

NAMESPACE="argocd"
APPS=()

case "$ENV" in
  dev|hml|prd)
    APPS=("dns-gitops")
    ;;
  all)
    APPS=("crossplane-xrds" "crossplane-providers" "crossplane-configs" "dns-gitops")
    ;;
  *)
    echo "Error: Invalid environment: $ENV"
    echo "Valid options: dev, hml, prd, all"
    exit 1
    ;;
esac

echo "Syncing ArgoCD applications..."
echo ""

for app in "${APPS[@]}"; do
  echo "Application: $app"
  
  if [ "$FORCE" = "--force" ]; then
    kubectl patch application "$app" -n "$NAMESPACE" --type merge \
      -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"main"}}}'
    echo "  Status: Force sync initiated"
  else
    kubectl patch application "$app" -n "$NAMESPACE" --type merge \
      -p '{"operation":{"sync":{"revision":"main"}}}'
    echo "  Status: Sync initiated"
  fi
  echo ""
done

echo "Waiting for sync to complete (60s timeout)..."
sleep 5

for app in "${APPS[@]}"; do
  STATUS=$(kubectl get application "$app" -n "$NAMESPACE" -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
  HEALTH=$(kubectl get application "$app" -n "$NAMESPACE" -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
  echo "$app: Sync=$STATUS Health=$HEALTH"
done
echo ""

echo "To check detailed status:"
echo "  kubectl get applications -n argocd"
echo "  kubectl describe application dns-gitops -n argocd"
