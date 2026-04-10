# AWS DNS Crossplane POC - APE Platform Aligned

> **⚠️ MIGRATION NOTICE**: This repository has been restructured to align with APE platform standards (2026-04-10).
>
> - **API Group Changed**: `dns.crossplane.poc` → `dock.tech`
> - **New Structure**: Helm charts instead of loose YAML files
> - **Hierarchy Required**: All resources need domain/subdomain/system fields
> - **See**: `docs/IMPLEMENTATION-PLAN-APE-ALIGNMENT.md` for full migration details

## Overview

Kubernetes-native DNS management for AWS Route53 using Crossplane, aligned with APE platform organizational hierarchy.

## Quick Start

### Install All Charts

```bash
# 1. Install providers
helm install crossplane-providers ./crossplane-providers \
  --namespace crossplane-system \
  --create-namespace

# 2. Install functions
helm install crossplane-functions ./crossplane-functions \
  --namespace crossplane-system

# 3. Install provider configs (update values.yaml first!)
helm install crossplane-provider-config-aws ./crossplane-provider-config-aws \
  --namespace crossplane-system

# 4. Install DNS compositions
helm install crossplane-dns ./crossplane-compositions-dns \
  --namespace crossplane-system
```

### Create a DNS Zone

```yaml
apiVersion: dock.tech/v1
kind: DNSZone
metadata:
  name: myapp-zone-dev
  namespace: cross-cloud-myapp
spec:
  # Hierarchy (required - APE platform)
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev

  # AWS (required - APE platform)
  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  # DNS (required)
  zoneName: myapp.dev.dock.tech
  comment: "My application DNS zone"

  # Optional: DNS records (batch creation)
  records:
    - name: api
      type: A
      ttl: 300
      values:
        - "10.0.1.50"
```

## Repository Structure

```
aws-dns-crossplane-poc/
├── crossplane-compositions-dns/     # Main DNS chart
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── README.md                    # Detailed usage guide
│   ├── templates/
│   │   ├── crds/
│   │   │   ├── dnszone.yaml         # DNSZone XRD (dock.tech/v1)
│   │   │   └── dnsrequest.yaml      # DNSRequest XRD (dock.tech/v1)
│   │   └── compositions/
│   │       ├── dnszone-batch.yaml   # Batch creation with CloudFormation
│   │       └── dnszone-observe.yaml # Import existing zones
│   └── tests/
│       ├── dnszone-minimal.yaml
│       └── dnszone-with-records.yaml
│
├── crossplane-providers/            # Provider installation chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       └── providers.yaml           # AWS Route53 + CloudFormation providers
│
├── crossplane-provider-config-aws/  # AWS config chart
│   ├── Chart.yaml
│   ├── values.yaml                  # UPDATE with actual AWS account IDs!
│   └── templates/
│       └── provider-config.yaml     # ProviderConfig + EnvironmentConfig
│
├── crossplane-functions/            # Functions chart
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       └── functions.yaml           # go-templating, auto-ready, environment-configs
│
├── docs/
│   ├── IMPLEMENTATION-PLAN-APE-ALIGNMENT.md  # Complete migration plan
│   ├── PLATFORM-ALIGNMENT-ANALYSIS.md        # Pattern analysis
│   └── QUICK-ALIGNMENT-SUMMARY.md            # TL;DR
│
└── .github/workflows/
    └── build.yaml                   # CI/CD for Helm charts
```

## Key Changes from Original

### API Group

- **Old**: `dns.crossplane.poc/v1alpha1`
- **New**: `dock.tech/v1`

### Required Fields (NEW)

All resources now require APE platform hierarchy fields:

```yaml
spec:
  domain: cross          # NEW
  subdomain: cloud       # NEW
  system: myapp          # NEW
  environment: dev       # Existing, now enum
  aws:                   # NEW
    account: 123456789012
    accountName: dev-account
    region: us-east-2
```

### Provider Configs

- **Old**: `aws-dev`, `aws-hml`, `aws-prd` (namespaced ProviderConfig)
- **New**: `dev-account`, `hml-account`, `prd-account` (ProviderConfig with IRSA)

### EnvironmentConfig Integration

Compositions now use `environment-configs` function to dynamically lookup AWS accounts instead of hardcoding.

### Automatic Tagging

All AWS resources automatically tagged with:

```yaml
tags:
  createdBy: ape-platform
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev
```

## Documentation

- **Chart README**: `crossplane-compositions-dns/README.md` - Complete usage guide
- **Migration Plan**: `docs/IMPLEMENTATION-PLAN-APE-ALIGNMENT.md` - 4-week plan
- **Analysis**: `docs/PLATFORM-ALIGNMENT-ANALYSIS.md` - Why these changes
- **Quick Summary**: `docs/QUICK-ALIGNMENT-SUMMARY.md` - TL;DR

## Configuration

### Update Provider Config Values

Before installing, edit `crossplane-provider-config-aws/values.yaml`:

```yaml
configs:
  - name: dev-account
    roleARN: arn:aws:iam::YOUR_DEV_ACCOUNT:role/crossplane-dns  # UPDATE THIS
    envs:
      aws:
        account: YOUR_DEV_ACCOUNT_ID                             # UPDATE THIS
        accountName: dev-account
        region: us-east-2
```

### IRSA Setup (Recommended)

Create IAM roles in each AWS account with Route53 permissions and EKS trust relationship.

## Testing

```bash
# Lint all charts
for chart in crossplane-*/; do helm lint "$chart"; done

# Template charts
helm template test crossplane-compositions-dns --debug

# Validate test manifests
kubectl apply --dry-run=server -f crossplane-compositions-dns/tests/dnszone-minimal.yaml
```

## Migration from Old Structure

See `docs/IMPLEMENTATION-PLAN-APE-ALIGNMENT.md` for complete migration guide.

**Summary**:
1. Old XRDs remain in `platform/` directory (deprecated)
2. New Helm charts in `crossplane-*/` directories
3. Update existing resources with hierarchy fields
4. Change API group to `dock.tech`
5. Recreate resources (breaking change)

## CI/CD

GitHub Actions workflow validates all charts on PR:

- Helm lint
- Helm template
- YAML syntax validation

See `.github/workflows/build.yaml`

## Support

- **Repository**: https://github.com/dock-tech/aws-dns-crossplane-poc
- **Issues**: https://github.com/dock-tech/aws-dns-crossplane-poc/issues
- **Maintainer**: APE Platform Team (platform@dock.tech)

## License

Proprietary - Dock.tech Internal Use Only
