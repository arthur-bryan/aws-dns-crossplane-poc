#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLUSTER_NAME="ape-dns-lab"

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "kind cluster '$CLUSTER_NAME' already exists — skipping create"
else
  echo ">>> creating kind cluster '$CLUSTER_NAME'"
  kind create cluster --config "$LAB_DIR/kind/cluster.yaml" --wait 180s
fi

kubectl config use-context "kind-$CLUSTER_NAME"
kubectl wait --for=condition=Ready nodes --all --timeout=120s
echo ">>> kind cluster ready"
