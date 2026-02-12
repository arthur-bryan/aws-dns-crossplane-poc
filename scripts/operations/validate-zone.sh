#!/bin/bash
# Validate zone YAML before applying to cluster

set -e

ZONE_FILE="$1"

if [ -z "$ZONE_FILE" ]; then
  echo "Usage: $0 <zone-yaml-file>"
  echo ""
  echo "Examples:"
  echo "  $0 gitops/dev/infradev.hml.dock.tech.yaml"
  echo "  $0 gitops/hml/infrahml.hml.dock.tech.yaml"
  exit 1
fi

if [ ! -f "$ZONE_FILE" ]; then
  echo "Error: File not found: $ZONE_FILE"
  exit 1
fi

echo "Validating: $ZONE_FILE"
echo ""

ERRORS=0

echo "1. Checking YAML syntax..."
if ! yq eval '.' "$ZONE_FILE" > /dev/null 2>&1; then
  echo "   ERROR: Invalid YAML syntax"
  ERRORS=$((ERRORS + 1))
else
  echo "   OK: Valid YAML"
fi
echo ""

echo "2. Checking required fields..."
ZONE_NAME=$(yq eval '.spec.zoneName' "$ZONE_FILE")
ENVIRONMENT=$(yq eval '.spec.environment' "$ZONE_FILE")
EXTERNAL_NAME=$(yq eval '.metadata.annotations["crossplane.io/external-name"]' "$ZONE_FILE")

if [ "$ZONE_NAME" = "null" ] || [ -z "$ZONE_NAME" ]; then
  echo "   ERROR: Missing spec.zoneName"
  ERRORS=$((ERRORS + 1))
else
  echo "   OK: zoneName=$ZONE_NAME"
fi

if [ "$ENVIRONMENT" = "null" ] || [ -z "$ENVIRONMENT" ]; then
  echo "   ERROR: Missing spec.environment"
  ERRORS=$((ERRORS + 1))
else
  echo "   OK: environment=$ENVIRONMENT"
fi

if [ "$EXTERNAL_NAME" = "null" ] || [ -z "$EXTERNAL_NAME" ]; then
  echo "   ERROR: Missing crossplane.io/external-name annotation"
  ERRORS=$((ERRORS + 1))
else
  echo "   OK: external-name=$EXTERNAL_NAME"
fi
echo ""

echo "3. Validating DNS records..."
RECORD_COUNT=$(yq eval '.spec.records | length' "$ZONE_FILE")
if [ "$RECORD_COUNT" = "null" ] || [ "$RECORD_COUNT" = "0" ]; then
  echo "   WARNING: No records defined"
else
  echo "   OK: $RECORD_COUNT records"
  
  DUPLICATE_NAMES=$(yq eval '.spec.records[].name' "$ZONE_FILE" | sort | uniq -d)
  if [ ! -z "$DUPLICATE_NAMES" ]; then
    echo "   WARNING: Duplicate record names found:"
    echo "$DUPLICATE_NAMES" | sed 's/^/     - /'
  fi
fi
echo ""

echo "4. Checking Kubernetes dry-run..."
if kubectl apply --dry-run=server -f "$ZONE_FILE" > /dev/null 2>&1; then
  echo "   OK: Kubernetes validation passed"
else
  echo "   ERROR: Kubernetes validation failed"
  kubectl apply --dry-run=server -f "$ZONE_FILE" 2>&1 | grep -v "^$" || true
  ERRORS=$((ERRORS + 1))
fi
echo ""

if [ $ERRORS -eq 0 ]; then
  echo "Validation: PASSED"
  echo ""
  echo "Next steps:"
  echo "  git add $ZONE_FILE"
  echo "  git commit -m \"Add/update zone $ZONE_NAME\""
  echo "  git push origin main"
  echo "  ./scripts/operations/sync-gitops.sh"
  exit 0
else
  echo "Validation: FAILED ($ERRORS errors)"
  exit 1
fi
