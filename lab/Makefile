# Local lab for APE DNS Crossplane POC
# Usage: make -C lab up | down | status | logs
#
# Phase-scoped targets are provided so you can re-run individual steps.

SHELL := /usr/bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

CLUSTER_NAME := ape-dns-lab
REPO_URL     := https://github.com/arthur-bryan/aws-dns-crossplane-poc
REPO_BRANCH  := feature/ape-platform-alignment

.PHONY: help
help:
	@echo "targets:"
	@echo "  up              — full bring-up (phases 1→5)"
	@echo "  pause           — docker stop the kind node (state preserved)"
	@echo "  resume          — docker start the kind node (~30s back up)"
	@echo "  down            — DELETE the kind cluster (destructive; ~5m rebuild next time)"
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

.PHONY: pause
pause:
	@echo ">>> pausing kind node (state preserved)"
	docker stop $(CLUSTER_NAME)-control-plane
	@pgrep -f "backstage-cli repo start" >/dev/null 2>&1 && pkill -f "backstage-cli repo start" || true
	@echo ">>> paused. 'make -C lab resume' to bring it back (~30s)"

.PHONY: resume
resume:
	@echo ">>> resuming kind node"
	docker start $(CLUSTER_NAME)-control-plane
	@echo ">>> waiting for API server"
	@until kubectl --context kind-$(CLUSTER_NAME) get nodes >/dev/null 2>&1; do sleep 2; done
	kubectl --context kind-$(CLUSTER_NAME) wait --for=condition=Ready nodes --all --timeout=120s
	@echo ">>> ready. Backstage (if needed): cd lab/backstage/ape-lab && GITHUB_TOKEN=... yarn start"

.PHONY: down
down:
	@echo ">>> DELETING kind cluster '$(CLUSTER_NAME)' (destructive — state lost)"
	@echo ">>> use 'make -C lab pause' instead for a fast-resumable stop"
	@echo ""
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
