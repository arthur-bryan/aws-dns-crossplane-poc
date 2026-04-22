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
	@echo "  up                — full bring-up (phases 1→5 + Backstage)"
	@echo "  pause             — stop Backstage + docker stop kind node (state preserved)"
	@echo "  resume            — docker start kind + start Backstage (~60-90s)"
	@echo "  down              — DELETE the kind cluster (destructive; ~5m rebuild next time)"
	@echo "  status            — cluster + argo + crossplane + backstage status"
	@echo ""
	@echo "  backstage-up      — start Backstage detached in background"
	@echo "  backstage-down    — stop Backstage"
	@echo "  backstage-log     — tail the Backstage log"
	@echo ""
	@echo "  autostart-on      — kind node auto-starts on Docker daemon start (after PC boot)"
	@echo "  autostart-off     — kind node stays stopped on PC boot (default)"
	@echo ""
	@echo "  phase1-kind       — create kind cluster + ingress-nginx"
	@echo "  phase2-xplane     — install Crossplane + Functions"
	@echo "  phase3-argocd     — install ArgoCD + ingress"
	@echo "  phase5-apps       — apply App-of-Apps"
	@echo ""
	@echo "  aws-creds         — create aws-creds secret (reads ~/.aws/credentials)"
	@echo "  argo-password     — print argocd admin initial password"
	@echo "  argo-port         — port-forward argocd server to :8081"

.PHONY: up
up: phase1-kind phase2-xplane phase3-argocd phase5-apps
	@echo ""
	@echo "=== lab ready ==="
	@echo "argocd UI : http://argocd.localtest.me (or 'make argo-port' → http://localhost:8081)"
	@echo "admin pw  : make argo-password"
	@echo ""
	@echo "Next:"
	@echo "  make aws-creds    (after ~/.aws/credentials is populated)"
	@echo "  make backstage-up (starts Backstage; needs gh auth login or GITHUB_TOKEN)"
	@echo "  make autostart-on (optional: kind auto-starts on PC boot)"

.PHONY: pause
pause:
	@echo ">>> stopping Backstage"
	@bash bootstrap/backstage-down.sh
	@echo ">>> pausing kind node (state preserved)"
	@docker container inspect $(CLUSTER_NAME)-control-plane >/dev/null 2>&1 || { echo "no kind container '$(CLUSTER_NAME)-control-plane' to pause"; exit 0; }
	docker stop $(CLUSTER_NAME)-control-plane >/dev/null
	@echo ">>> paused. 'make -C lab resume' to bring it back"

.PHONY: resume
resume:
	@echo ">>> resuming kind node"
	@docker container inspect $(CLUSTER_NAME)-control-plane >/dev/null 2>&1 || { echo "ERROR: no kind container '$(CLUSTER_NAME)-control-plane'. Was it deleted? Run 'make -C lab up'."; exit 1; }
	docker start $(CLUSTER_NAME)-control-plane >/dev/null
	@echo ">>> waiting for API server"
	@for i in $$(seq 1 60); do
	  if kubectl --context kind-$(CLUSTER_NAME) get --raw /healthz >/dev/null 2>&1; then
	    break
	  fi
	  if [ "$$i" = "60" ]; then echo "ERROR: API server didn't come up within 120s"; exit 1; fi
	  sleep 2
	done
	kubectl --context kind-$(CLUSTER_NAME) wait --for=condition=Ready nodes --all --timeout=60s
	@echo ">>> starting Backstage"
	@bash bootstrap/backstage-up.sh
	@echo ""
	@echo ">>> lab resumed"
	@echo "    argocd    : http://argocd.localtest.me"
	@echo "    backstage : http://localhost:3000 (~60-90s to finish bundling)"

.PHONY: backstage-up
backstage-up:
	@bash bootstrap/backstage-up.sh

.PHONY: backstage-down
backstage-down:
	@bash bootstrap/backstage-down.sh

.PHONY: backstage-log
backstage-log:
	@test -f backstage/backstage.log || { echo "no log yet (backstage never started)"; exit 1; }
	tail -f backstage/backstage.log

.PHONY: autostart-on
autostart-on:
	@docker container inspect $(CLUSTER_NAME)-control-plane >/dev/null 2>&1 || { echo "ERROR: kind container not found"; exit 1; }
	docker update --restart unless-stopped $(CLUSTER_NAME)-control-plane >/dev/null
	@echo ">>> kind node will auto-start when the Docker daemon starts (i.e. after PC boot)"
	@echo ">>> Backstage still needs 'make -C lab backstage-up' after boot"

.PHONY: autostart-off
autostart-off:
	@docker container inspect $(CLUSTER_NAME)-control-plane >/dev/null 2>&1 || { echo "ERROR: kind container not found"; exit 1; }
	docker update --restart no $(CLUSTER_NAME)-control-plane >/dev/null
	@echo ">>> kind node will NOT auto-start; use 'make -C lab resume' after PC boot"

.PHONY: down
down:
	@echo ">>> DELETING kind cluster '$(CLUSTER_NAME)' (destructive — state lost)"
	@echo ">>> use 'make -C lab pause' instead for a fast-resumable stop"
	@echo ""
	kind delete cluster --name $(CLUSTER_NAME)

.PHONY: status
status:
	@echo "--- kind container ---"
	@docker ps -a --filter "name=$(CLUSTER_NAME)-control-plane" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true
	@echo
	@echo "--- kind restart policy (autostart?) ---"
	@docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' $(CLUSTER_NAME)-control-plane 2>/dev/null || echo "(not created)"
	@echo
	@echo "--- nodes ---"
	@kubectl get nodes 2>/dev/null || echo "(api not reachable)"
	@echo
	@echo "--- crossplane ---"; kubectl -n crossplane-system get pods 2>/dev/null || true
	@echo "--- functions ---"; kubectl get functions.pkg.crossplane.io 2>/dev/null || true
	@echo "--- providers ---"; kubectl get providers.pkg.crossplane.io 2>/dev/null || true
	@echo "--- xrds ---"; kubectl get xrd 2>/dev/null || true
	@echo "--- argocd apps ---"; kubectl -n argocd get applications 2>/dev/null || true
	@echo
	@echo "--- backstage ---"
	@if [ -f backstage/backstage.pid ] && kill -0 "$$(cat backstage/backstage.pid)" 2>/dev/null; then
	  echo "running (pid $$(cat backstage/backstage.pid))"
	elif command -v lsof >/dev/null 2>&1; then
	  pid=$$(lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null | head -1)
	  if [ -n "$$pid" ]; then
	    echo "running (orphan listener pid $$pid)"
	  else
	    echo "not running"
	  fi
	else
	  echo "not running (no lsof; can't verify)"
	fi

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
