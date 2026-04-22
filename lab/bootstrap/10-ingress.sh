#!/usr/bin/env bash
set -euo pipefail

echo ">>> installing ingress-nginx (kind manifest)"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/kind/deploy.yaml

echo ">>> waiting for ingress-nginx controller"
kubectl -n ingress-nginx wait --for=condition=Ready pod \
  -l app.kubernetes.io/component=controller \
  --timeout=300s

echo ">>> ingress-nginx ready"
