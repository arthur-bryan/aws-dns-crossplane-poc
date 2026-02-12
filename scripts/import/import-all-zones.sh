#!/bin/bash
# Automated DNS Zone Import Script
# Discovers Route53 records and updates Crossplane manifests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Zone configuration
declare -A ZONES=(
    ["dev"]="Z042057136AZ7P05F0XOW:dnszone-dev:infradev.hml.dock.tech"
    ["hml"]="Z07088012G012PYYZ2302:dnszone-hml:infrahml.hml.dock.tech"
    ["prd"]="Z0195231ON0MEFO4W8P4:dnszone-prd:infraprd.hml.dock.tech"
)

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install it."
        exit 1
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not found. Please install it."
        exit 1
    fi

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_warn "kubectl not found. k8s validation will be skipped."
    fi

    log_info "Prerequisites OK"
}

check_aws_credentials() {
    local env="$1"
    local profile="$2"

    log_info "Checking AWS credentials for $env (profile: $profile)..."

    # Check if profile exists
    if ! aws configure list-profiles | grep -q "^${profile}$"; then
        log_error "AWS profile '$profile' not found."
        log_info "Available profiles:"
        aws configure list-profiles | sed 's/^/  /'
        return 1
    fi

    # Test credentials
    if ! aws sts get-caller-identity --profile "$profile" &>/dev/null; then
        log_error "AWS credentials for profile '$profile' are invalid or expired."
        log_info "Try running: aws sso login --profile $profile"
        return 1
    fi

    log_info "AWS credentials OK for $env"
    return 0
}

discover_zone_records() {
    local zone_id="$1"
    local profile="$2"
    local output_file="$3"

    log_info "Discovering records for zone $zone_id..."

    if ! "$SCRIPT_DIR/discover-zones.py" "$zone_id" "$profile" 2>/dev/null > "$output_file"; then
        log_error "Failed to discover records for zone $zone_id"
        return 1
    fi

    local record_count=$(grep -c '^    - name:' "$output_file" || echo 0)
    log_info "Discovered $record_count records"

    return 0
}

update_manifest() {
    local env="$1"
    local zone_name="$2"
    local records_file="$3"

    local manifest_file="$PROJECT_ROOT/gitops/$env/${zone_name}.yaml"

    log_info "Updating manifest: $manifest_file"

    # Check if manifest exists
    if [ ! -f "$manifest_file" ]; then
        log_error "Manifest file not found: $manifest_file"
        return 1
    fi

    # Create backup
    cp "$manifest_file" "${manifest_file}.backup-$(date +%Y%m%d-%H%M%S)"

    # Check if records section exists
    if grep -q "^  records:" "$manifest_file"; then
        log_warn "Manifest already has records section. Manual merge required."
        log_info "Discovered records saved to: $records_file"
        log_info "Backup created: ${manifest_file}.backup-*"
        return 1
    fi

    # Append records to manifest
    {
        # Remove records section if it exists (empty)
        grep -v "^  records:" "$manifest_file" || cat "$manifest_file"
        echo ""
        echo "  # Complete records imported from Route53 on $(date +%Y-%m-%d)"
        echo "  # Generated with: scripts/discover-zones.py"
        echo "  records:"
        cat "$records_file"
    } > "${manifest_file}.new"

    # Replace original with new version
    mv "${manifest_file}.new" "$manifest_file"

    log_info "Manifest updated successfully"
    return 0
}

validate_yaml() {
    local manifest_file="$1"

    log_info "Validating YAML syntax..."

    if command -v kubectl &> /dev/null; then
        if kubectl apply --dry-run=client -f "$manifest_file" &>/dev/null; then
            log_info "YAML validation passed"
            return 0
        else
            log_error "YAML validation failed"
            kubectl apply --dry-run=client -f "$manifest_file"
            return 1
        fi
    else
        log_warn "kubectl not available, skipping YAML validation"
        return 0
    fi
}

process_zone() {
    local env="$1"
    local zone_config="${ZONES[$env]}"

    IFS=':' read -r zone_id profile zone_name <<< "$zone_config"

    log_info "========================================="
    log_info "Processing $env zone: $zone_name"
    log_info "========================================="

    # Check credentials
    if ! check_aws_credentials "$env" "$profile"; then
        log_warn "Skipping $env zone due to credential issues"
        return 1
    fi

    # Discover records
    local records_file="/tmp/${zone_name//./-}-records.yaml"
    if ! discover_zone_records "$zone_id" "$profile" "$records_file"; then
        log_error "Failed to discover records for $env zone"
        return 1
    fi

    # Update manifest
    local manifest_file="$PROJECT_ROOT/gitops/$env/${zone_name}.yaml"
    if ! update_manifest "$env" "$zone_name" "$records_file"; then
        log_warn "Manifest update failed or requires manual intervention"
        log_info "Records saved to: $records_file"
        return 1
    fi

    # Validate YAML
    if ! validate_yaml "$manifest_file"; then
        log_error "YAML validation failed for $env zone"
        return 1
    fi

    log_info "Successfully processed $env zone"
    return 0
}

main() {
    echo ""
    log_info "DNS Zone Import Automation Script"
    echo ""

    check_prerequisites

    # Process zones
    local success_count=0
    local failed_count=0

    for env in dev hml prd; do
        if process_zone "$env"; then
            ((success_count++))
        else
            ((failed_count++))
        fi
        echo ""
    done

    # Summary
    log_info "========================================="
    log_info "Import Summary"
    log_info "========================================="
    log_info "Successful: $success_count zones"
    log_info "Failed: $failed_count zones"

    if [ $failed_count -gt 0 ]; then
        log_warn "Some zones failed to import. See errors above."
        log_info "For failed zones, you can:"
        log_info "  1. Refresh AWS credentials: aws sso login --profile <profile>"
        log_info "  2. Manually run: ./scripts/discover-zones.py <zone-id> <profile>"
        log_info "  3. Manually update manifests in gitops/<env>/"
        echo ""
        log_info "See docs/IMPORT-GUIDE.md for detailed instructions"
    fi

    echo ""
    log_info "Next steps:"
    log_info "  1. Review updated manifests in gitops/<env>/"
    log_info "  2. Verify composition uses Observe mode:"
    log_info "     grep 'compositionRef:' gitops/*/*.yaml"
    log_info "  3. Apply to k8s cluster:"
    log_info "     kubectl apply -f gitops/dev/"
    log_info "     kubectl apply -f gitops/hml/"
    log_info "     kubectl apply -f gitops/prd/"
    log_info "  4. Validate no AWS changes:"
    log_info "     See docs/IMPORT-GUIDE.md Section: Validate Observe Mode"
    log_info "  5. Plan migration to Update mode:"
    log_info "     See docs/MIGRATION-OBSERVE-TO-UPDATE.md"
    echo ""

    exit $failed_count
}

# Run main
main "$@"
