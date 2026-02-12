#!/bin/bash
# ArgoCD + DNS Zone Deployment Script
# Automated deployment with validation

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check prerequisites
log_step "1/6 Checking prerequisites..."

if ! command -v kubectl &> /dev/null; then
    log_error "kubectl not found. Please install kubectl."
    exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
    log_error "Cannot connect to Kubernetes cluster. Is it running?"
    log_info "Try: sudo systemctl start k3s (or your cluster)"
    exit 1
fi

log_info "✅ kubectl and cluster accessible"

# Install ArgoCD
log_step "2/6 Installing ArgoCD..."

if kubectl get namespace argocd &> /dev/null; then
    log_warn "ArgoCD namespace already exists. Skipping installation."
else
    log_info "Creating argocd namespace..."
    kubectl create namespace argocd

    log_info "Installing ArgoCD (this takes 3-5 minutes)..."
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

    log_info "Waiting for ArgoCD to be ready..."
    kubectl wait --for=condition=Available --timeout=600s deployment/argocd-server -n argocd

    log_info "✅ ArgoCD installed successfully"
fi

# Get ArgoCD admin password
log_step "3/6 Retrieving ArgoCD credentials..."

ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d)

if [ -n "$ARGOCD_PASSWORD" ]; then
    log_info "✅ ArgoCD admin password retrieved"
    echo ""
    echo "========================================="
    echo "ArgoCD Login Credentials:"
    echo "URL: https://localhost:8080"
    echo "Username: admin"
    echo "Password: $ARGOCD_PASSWORD"
    echo "========================================="
    echo ""
else
    log_warn "Could not retrieve admin password. May need manual retrieval."
fi

# Deploy root-app
log_step "4/6 Deploying root-app (App-of-Apps)..."

if kubectl get application root-app -n argocd &> /dev/null; then
    log_warn "root-app already exists. Updating..."
    kubectl apply -f "$SCRIPT_DIR/platform/argocd/bootstrap/root-app.yaml"
else
    log_info "Creating root-app..."
    kubectl apply -f "$SCRIPT_DIR/platform/argocd/bootstrap/root-app.yaml"
fi

log_info "✅ root-app deployed"

# Wait for applications to sync
log_step "5/6 Waiting for applications to deploy (sync waves 0→1→2→3)..."

log_info "This takes 10-15 minutes. Monitoring progress..."

# Function to check app status
check_app() {
    local app_name=$1
    local timeout=300
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local status=$(kubectl get application "$app_name" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
        local health=$(kubectl get application "$app_name" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")

        if [ "$status" = "Synced" ] && [ "$health" = "Healthy" ]; then
            log_info "✅ $app_name: Synced and Healthy"
            return 0
        fi

        echo -ne "\r  $app_name: $status / $health (${elapsed}s elapsed)..."
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
log_step "6/6 Verifying DNS zones deployed..."

log_info "Waiting for dns-system namespace..."
kubectl wait --for=condition=Ready --timeout=60s namespace/dns-system 2>/dev/null || log_warn "Namespace not ready yet"

log_info "Checking DNS zones..."
sleep 10

ZONES=$(kubectl get dnszone -n dns-system --no-headers 2>/dev/null | wc -l)

if [ "$ZONES" -eq 3 ]; then
    log_info "✅ All 3 DNS zones deployed:"
    kubectl get dnszone -n dns-system
else
    log_warn "⚠️  Expected 3 zones, found $ZONES"
    kubectl get dnszone -n dns-system 2>/dev/null || log_error "No zones found"
fi

# Final summary
echo ""
echo "========================================="
echo "DEPLOYMENT COMPLETE!"
echo "========================================="
echo ""
log_info "Next steps:"
echo "  1. Access ArgoCD UI:"
echo "     kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "     https://localhost:8080 (admin / $ARGOCD_PASSWORD)"
echo ""
echo "  2. View applications:"
echo "     kubectl get applications -n argocd"
echo ""
echo "  3. Check DNS zones:"
echo "     kubectl get dnszone -n dns-system"
echo ""
echo "  4. Verify observe mode (NO AWS changes):"
echo "     aws route53 list-resource-record-sets --hosted-zone-id Z042057136AZ7P05F0XOW --profile dnszone-dev-sso --query 'length(ResourceRecordSets)'"
echo ""
log_info "All systems deployed! 🚀"
