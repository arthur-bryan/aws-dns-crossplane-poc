#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ARGOCD_CHART_VERSION="${ARGOCD_CHART_VERSION:-7.7.7}"

echo ">>> adding argo helm repo"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null
helm repo update >/dev/null

echo ">>> installing argocd"
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace \
  --version "${ARGOCD_CHART_VERSION}" \
  -f "$LAB_DIR/argocd/values.yaml" \
  --wait \
  --timeout 10m

echo ">>> waiting for argocd-server pod"
kubectl -n argocd wait --for=condition=Available --timeout=300s deploy/argocd-server

echo ">>> applying catch-all ingress (raw-IP access, no hosts-file needed)"
kubectl apply -f "$LAB_DIR/argocd/ingress-ip-catchall.yaml"

echo ""
echo ">>> argocd ready"
echo "    UI         : http://argocd.localtest.me"
echo "                 http://<LAN_IP>/               (also works from other PCs)"
echo "    user       : admin"
echo "    password   : kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
