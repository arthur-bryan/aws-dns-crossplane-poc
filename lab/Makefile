# Local lab for APE DNS Crossplane POC
# Usage: make -C lab up | down | status | logs
#
# Phase-scoped targets are provided so you can re-run individual steps.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

CLUSTER_NAME := ape-dns-lab
REPO_URL     := https://github.com/arthur-bryan/aws-dns-crossplane-poc
REPO_BRANCH  := feature/ape-platform-alignment

.PHONY: help
help:
	@echo "targets:"
	@echo "  up              — full bring-up (phases 1→5)"
	@echo "  down            — delete kind cluster"
	@echo "  status          — cluster + argo + crossplane status"
	@echo ""
	@echo "  phase1-kind     — create kind cluster + ingress-nginx"
	@echo "  phase2-xplane   — install Crossplane + Functions"
	@echo "  phase3-argocd   — install ArgoCD + ingress"
	@echo "  phase5-apps     — apply App-of-Apps"
	@echo ""
	@echo "  aws-creds       — create aws-creds secret (reads ~/.aws/credentials)"
	@echo "  argo-password   — print argocd admin initial password"
	@echo "  argo-port       — port-forward argocd server to :8081"

.PHONY: up
up: phase1-kind phase2-xplane phase3-argocd phase5-apps
	@echo ""
	@echo "=== lab ready ==="
	@echo "argocd UI : http://argocd.localtest.me (or 'make argo-port' → http://localhost:8081)"
	@echo "admin pw  : make argo-password"
	@echo ""
	@echo "Next: 'make aws-creds' (after you create ~/.aws/credentials for the target account)"

.PHONY: down
down:
	kind delete cluster --name $(CLUSTER_NAME)

.PHONY: status
status:
	@echo "--- nodes ---"; kubectl get nodes || true
	@echo "--- crossplane ---"; kubectl -n crossplane-system get pods 2>/dev/null || true
	@echo "--- functions ---"; kubectl get functions.pkg.crossplane.io 2>/dev/null || true
	@echo "--- providers ---"; kubectl get providers.pkg.crossplane.io 2>/dev/null || true
	@echo "--- xrds ---"; kubectl get xrd 2>/dev/null || true
	@echo "--- argocd apps ---"; kubectl -n argocd get applications 2>/dev/null || true

.PHONY: phase1-kind
phase1-kind:
	bash bootstrap/00-kind.sh
	bash bootstrap/10-ingress.sh

.PHONY: phase2-xplane
phase2-xplane:
	bash bootstrap/20-crossplane.sh

.PHONY: phase3-argocd
phase3-argocd:
	bash bootstrap/30-argocd.sh

.PHONY: phase5-apps
phase5-apps:
	kubectl apply -f argocd/root-app.yaml

.PHONY: aws-creds
aws-creds:
	@if [ ! -f "$$HOME/.aws/credentials" ]; then
	  echo "ERROR: ~/.aws/credentials not found. Create it with the target account creds first."
	  exit 1
	fi
	kubectl -n crossplane-system create secret generic aws-creds \
	  --from-file=credentials=$$HOME/.aws/credentials \
	  --dry-run=client -o yaml | kubectl apply -f -
	@echo "aws-creds secret applied in crossplane-system"

.PHONY: argo-password
argo-password:
	@kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo

.PHONY: argo-port
argo-port:
	kubectl -n argocd port-forward svc/argocd-server 8081:443
