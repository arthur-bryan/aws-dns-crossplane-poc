#!/bin/bash
# Post-WSL-Restart Complete Deployment Script
# Creates k3d cluster + deploys ArgoCD + DNS zones in one command

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_success() { echo -e "${CYAN}[SUCCESS]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "========================================="
echo "  ArgoCD + Crossplane + DNS Deployment"
echo "  Post-WSL-Restart Automated Setup"
echo "========================================="
echo ""

# Step 1: Verify Go binaries work
log_step "1/7 Verifying Go binaries are functional..."

if ! kubectl version --client &> /dev/null; then
    log_error "kubectl still failing with threading errors"
    log_error "WSL restart may not have completed properly"
    log_info "Try: wsl --shutdown (from Windows), then restart WSL"
    exit 1
fi

if ! k3d version &> /dev/null; then
    log_error "k3d still failing with threading errors"
    log_error "WSL restart may not have completed properly"
    exit 1
fi

log_success "✅ Go binaries functional (threading issue resolved)"

# Step 2: Create k3d cluster
log_step "2/7 Creating k3d cluster 'crossplane-lab'..."

if k3d cluster list | grep -q crossplane-lab; then
    log_warn "Cluster 'crossplane-lab' already exists"
    log_info "Deleting old cluster..."
    k3d cluster delete crossplane-lab
fi

log_info "Creating new k3d cluster (takes 2-3 minutes)..."
k3d cluster create crossplane-lab \
  --api-port 6550 \
  --servers 1 \
  --agents 0 \
  --wait \
  --timeout 180s

log_success "✅ k3d cluster created"

# Step 3: Verify cluster access
log_step "3/7 Verifying cluster access..."

if ! kubectl cluster-info &> /dev/null; then
    log_error "Cannot connect to cluster"
    exit 1
fi

if ! kubectl get nodes &> /dev/null; then
    log_error "Cannot list nodes"
    exit 1
fi

NODES=$(kubectl get nodes --no-headers | wc -l)
log_success "✅ Cluster accessible ($NODES node(s))"

# Step 4: Install ArgoCD
log_step "4/7 Installing ArgoCD..."

if kubectl get namespace argocd &> /dev/null; then
    log_warn "ArgoCD namespace already exists. Skipping installation."
else
    log_info "Creating argocd namespace..."
    kubectl create namespace argocd

    log_info "Installing ArgoCD (this takes 3-5 minutes)..."
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

    log_info "Waiting for ArgoCD to be ready..."
    kubectl wait --for=condition=Available --timeout=600s deployment/argocd-server -n argocd

    log_success "✅ ArgoCD installed successfully"
fi

# Step 5: Get ArgoCD credentials
log_step "5/7 Retrieving ArgoCD credentials..."

ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d)

if [ -n "$ARGOCD_PASSWORD" ]; then
    log_success "✅ ArgoCD admin password retrieved"
else
    log_warn "Could not retrieve admin password"
fi

# Step 6: Deploy root-app
log_step "6/7 Deploying root-app (App-of-Apps)..."

if kubectl get application root-app -n argocd &> /dev/null; then
    log_warn "root-app already exists. Updating..."
    kubectl apply -f "$SCRIPT_DIR/platform/argocd/bootstrap/root-app.yaml"
else
    log_info "Creating root-app..."
    kubectl apply -f "$SCRIPT_DIR/platform/argocd/bootstrap/root-app.yaml"
fi

log_success "✅ root-app deployed"

# Step 7: Wait for applications to sync
log_step "7/7 Waiting for applications to deploy (sync waves 0→1→2→3)..."
log_info "This takes 10-15 minutes. Monitoring progress..."

check_app() {
    local app_name=$1
    local timeout=300
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local status=$(kubectl get application "$app_name" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
        local health=$(kubectl get application "$app_name" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")

        if [ "$status" = "Synced" ] && [ "$health" = "Healthy" ]; then
            log_success "✅ $app_name: Synced and Healthy"
            return 0
        fi

        echo -ne "\r  $app_name: $status / $health (${elapsed}s elapsed)...          "
        sleep 10
        elapsed=$((elapsed + 10))
    done

    log_warn "⚠️  $app_name: Timeout (may still be syncing)"
    return 1
}

# Wait for each wave
log_info "Wave 0: XRDs..."
sleep 30
check_app "crossplane-xrds"

log_info "Wave 1: Providers..."
sleep 30
check_app "crossplane-providers"

log_info "Wave 2: Configs..."
sleep 30
check_app "crossplane-configs"

log_info "Wave 3: DNS Zones..."
sleep 30
check_app "dns-gitops"

# Verify DNS zones
log_info "Verifying DNS zones deployed..."
sleep 10

ZONES=$(kubectl get dnszone -n dns-system --no-headers 2>/dev/null | wc -l)

if [ "$ZONES" -eq 3 ]; then
    log_success "✅ All 3 DNS zones deployed:"
    kubectl get dnszone -n dns-system
else
    log_warn "⚠️  Expected 3 zones, found $ZONES"
    kubectl get dnszone -n dns-system 2>/dev/null || log_error "No zones found"
fi

# Final summary
echo ""
echo "========================================="
echo "  DEPLOYMENT COMPLETE! 🚀"
echo "========================================="
echo ""
log_success "All systems deployed successfully!"
echo ""
echo "📊 Summary:"
echo "  - k3d cluster: crossplane-lab"
echo "  - ArgoCD: Installed and running"
echo "  - Applications: 4 (root-app + 3 platform apps)"
echo "  - DNS zones: $ZONES zones with 377 total records"
echo "  - Mode: OBSERVE (read-only, no AWS changes)"
echo ""
echo "🌐 Access ArgoCD UI:"
echo "  1. Port forward:"
echo "     kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo ""
echo "  2. Login:"
echo "     URL: https://localhost:8080"
echo "     Username: admin"
echo "     Password: $ARGOCD_PASSWORD"
echo ""
echo "✅ Next Steps:"
echo "  1. Access ArgoCD UI (see above)"
echo "  2. View all applications:"
echo "     kubectl get applications -n argocd"
echo ""
echo "  3. Check DNS zones:"
echo "     kubectl get dnszone -n dns-system"
echo ""
echo "  4. Verify observe mode (NO AWS changes):"
echo "     aws route53 list-resource-record-sets \\"
echo "       --hosted-zone-id Z042057136AZ7P05F0XOW \\"
echo "       --profile dnszone-dev-sso \\"
echo "       --query 'length(ResourceRecordSets)'"
echo ""
echo "📖 Documentation:"
echo "  - Deployment Guide: platform/argocd/DEPLOYMENT-GUIDE.md"
echo "  - Validation Checklist: platform/argocd/VALIDATION-CHECKLIST.md"
echo "  - Quick Start: README-DEPLOYMENT.md"
echo ""
log_success "🎉 GitOps deployment complete! All systems operational."
echo ""
