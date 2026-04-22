#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CROSSPLANE_VERSION="${CROSSPLANE_VERSION:-2.2.1}"

echo ">>> adding crossplane helm repo"
helm repo add crossplane-stable https://charts.crossplane.io/stable >/dev/null
helm repo update >/dev/null

echo ">>> installing crossplane v${CROSSPLANE_VERSION}"
helm upgrade --install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --version "${CROSSPLANE_VERSION}" \
  --wait

echo ">>> installing required Functions (go-templating, auto-ready)"
kubectl apply -f "$LAB_DIR/crossplane/functions.yaml"

echo ">>> waiting for Functions to be Healthy + Installed"
# Poll up to 180s for both conditions on both functions
for fn in crossplane-contrib-function-go-templating crossplane-contrib-function-auto-ready; do
  kubectl wait --for=condition=Healthy --timeout=180s function.pkg.crossplane.io/"$fn"
  kubectl wait --for=condition=Installed --timeout=180s function.pkg.crossplane.io/"$fn"
done

echo ">>> crossplane + functions ready"
kubectl get functions.pkg.crossplane.io
