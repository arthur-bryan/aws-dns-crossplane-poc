# Crossplane Compositions DNS

Helm chart for AWS Route53 DNS management via Crossplane, aligned with APE platform standards.

## Overview

This chart provides Composite Resource Definitions (XRDs) and Compositions for managing AWS Route53 DNS zones and records through the APE platform organizational hierarchy (Domain → SubDomain → System → Environment).

## Architecture

```
Domain (cross)
  └── SubDomain (cloud)
       └── System (dns-poc)
            ├── dev (Environment)
            │    └── test.dev.dock.tech (DNSZone)
            ├── hml (Environment)
            └── prd (Environment)
```

## Components

### Custom Resource Definitions (CRDs)

#### DNSZone (`dnszones.dock.tech`)

Manages Route53 hosted zones with batch record operations.

**API Group**: `dock.tech/v1`
**Kind**: `DNSZone`

**Required Fields**:
- `domain` - Parent domain (e.g., cross, saas, bass)
- `subdomain` - Parent subdomain (e.g., cloud, payments)
- `system` - Parent system (e.g., ape, dns-poc)
- `environment` - Target environment (dev, hml, poc, prd)
- `aws.account` - AWS account ID (12 digits)
- `aws.accountName` - AWS account name (matches ProviderConfig)
- `aws.region` - AWS region (default: us-east-2)
- `zoneName` - DNS zone FQDN

**Optional Fields**:
- `comment` - Zone description
- `tags` - Additional AWS tags (hierarchy tags added automatically)
- `records[]` - Batch record creation (max 500 for CloudFormation)

#### DNSRequest (`dnsrequests.dock.tech`)

Unified API for DNS operations (create/update/delete records).

**Actions Supported**:
- `create_record` - Create single record
- `update_record` - Update existing record
- `create_weighted_record` - Blue/green routing
- `create_alias_record` - ALIAS to CloudFront/ALB/NLB

## Installation

### Prerequisites

1. Crossplane 1.14+
2. Kubernetes cluster (EKS recommended)
3. AWS provider credentials (IRSA recommended)

### Install Dependencies First

```bash
# 1. Install providers
helm install crossplane-providers ./crossplane-providers \
  --namespace crossplane-system \
  --create-namespace

# Wait for providers to be healthy
kubectl wait --for=condition=Healthy provider.pkg.crossplane.io/upbound-provider-aws-route53 --timeout=5m

# 2. Install functions
helm install crossplane-functions ./crossplane-functions \
  --namespace crossplane-system

# 3. Install provider configs (update values.yaml with actual account IDs and role ARNs)
helm install crossplane-provider-config-aws ./crossplane-provider-config-aws \
  --namespace crossplane-system
```

### Install DNS Compositions Chart

```bash
helm install crossplane-dns ./crossplane-compositions-dns \
  --namespace crossplane-system
```

### Verify Installation

```bash
# Check XRDs installed
kubectl get xrd dnszones.dock.tech
kubectl get xrd dnsrequests.dock.tech

# Check compositions installed
kubectl get composition | grep dnszone
```

## Usage

### Example 1: Minimal DNS Zone

```yaml
apiVersion: dock.tech/v1
kind: DNSZone
metadata:
  name: myapp-zone-dev
  namespace: cross-cloud-myapp
spec:
  # Hierarchy (required)
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev

  # AWS (required)
  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  # DNS (required)
  zoneName: myapp.dev.dock.tech
```

### Example 2: Zone with Records

```yaml
apiVersion: dock.tech/v1
kind: DNSZone
metadata:
  name: myapp-zone-dev
  namespace: cross-cloud-myapp
spec:
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: myapp.dev.dock.tech
  comment: "My application DNS zone"

  # Optional: Additional tags
  tags:
    CostCenter: "Engineering"
    Owner: "MyApp Team"

  # Optional: DNS records (batch creation)
  records:
    - name: api
      type: A
      ttl: 300
      values:
        - "10.0.1.50"

    - name: www
      type: CNAME
      ttl: 300
      values:
        - "api.myapp.dev.dock.tech"
```

### Example 3: DNS Request

```yaml
apiVersion: dock.tech/v1
kind: DNSRequest
metadata:
  name: create-api-record
  namespace: cross-cloud-myapp
spec:
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  requesterName: platform-team@dock.tech
  action: create_record
  env: dev
  hostedzone: myapp.dev.dock.tech
  businessUnit: global
  originTicket: https://jira.dock.tech/browse/PLAT-123

  records:
    - name: api
      type: A
      value: "10.0.1.51"
      ttl: "300"
```

## Configuration

### values.yaml

```yaml
cluster:
  name: in-cluster

managementPolicies:
  - Observe
  - Create
  - Update
  - Delete

dns:
  defaultRegion: us-east-2
  defaultTTL: 300

compositions:
  batch: true
  observe: true
  manage: true
```

## Compositions

### dnszone-batch

Creates Route53 zone with batch record creation via CloudFormation.

**Use Cases**:
- New zones with multiple records (up to 500)
- Bulk record operations
- Dev/test environments

**Features**:
- CloudFormation stack for batch operations
- Automatic hierarchy tagging
- EnvironmentConfig integration

### dnszone-observe

Imports existing Route53 zones without modifications.

**Use Cases**:
- Importing existing zones
- Read-only observation
- Migration validation

**Features**:
- Observe-only management policy
- Orphan deletion policy (won't delete zone)

## EnvironmentConfig Integration

Compositions automatically pull AWS account info from EnvironmentConfigs created by System resources:

```yaml
# Created by crossplane-provider-config-aws chart
apiVersion: apiextensions.crossplane.io/v1alpha1
kind: EnvironmentConfig
metadata:
  name: dev-account
  labels:
    accountName: dev-account
data:
  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2
```

Compositions use this instead of hardcoding account names.

## Automatic Tagging

All Route53 resources are automatically tagged with hierarchy:

```yaml
tags:
  createdBy: ape-platform
  domain: cross
  subdomain: cloud
  system: myapp
  environment: dev
  # Plus any custom tags from spec.tags
```

## Limitations

1. **CloudFormation batch**: Max 500 records per zone
2. **ALIAS records**: Limited to CloudFront, ALB, NLB, S3
3. **Namespace**: Resources must be in system namespace

## Troubleshooting

### Issue: XRD not found

```bash
# Check XRDs installed
kubectl get xrd | grep dock.tech

# If missing, reinstall chart
helm upgrade --install crossplane-dns ./crossplane-compositions-dns
```

### Issue: Composition fails with "EnvironmentConfig not found"

```bash
# Check EnvironmentConfigs exist
kubectl get environmentconfig

# If missing, install provider-config chart
helm install crossplane-provider-config-aws ./crossplane-provider-config-aws
```

### Issue: IRSA authentication fails

```bash
# Check ServiceAccount has role ARN annotation
kubectl get sa -n crossplane-system provider-aws-route53 -o yaml | grep eks.amazonaws.com/role-arn

# If missing, update crossplane-providers values.yaml with actual role ARN
```

## Dependencies

This chart depends on:

1. **crossplane-providers** - Must be installed first
2. **crossplane-functions** - Must be installed second
3. **crossplane-provider-config-aws** - Must be installed third
4. **This chart** - Install last

## Migration from Old API Group

If migrating from `dns.crossplane.poc` to `dock.tech`:

1. Export existing resources:
   ```bash
   kubectl get dnszone -A -o yaml > backup.yaml
   ```

2. Update API group in YAML:
   ```bash
   sed -i 's/dns.crossplane.poc\/v1alpha1/dock.tech\/v1/g' backup.yaml
   ```

3. Add hierarchy fields manually to each resource

4. Recreate resources:
   ```bash
   kubectl apply -f backup.yaml
   ```

## Support

- Repository: https://github.com/dock-tech/aws-dns-crossplane-poc
- Issues: https://github.com/dock-tech/aws-dns-crossplane-poc/issues
- Maintainer: APE Platform Team (platform@dock.tech)

## License

Proprietary - Dock.tech Internal Use Only
