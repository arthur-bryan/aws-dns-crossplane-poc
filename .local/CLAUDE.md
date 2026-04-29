# AWS Route53 Crossplane Implementation - APE Platform Integration

**Project Type**: Production-Ready Crossplane Composition
**Purpose**: Self-service DNS zone and record management for APE Internal Developer Platform
**Status**: APE Platform Alignment Complete - Ready for Integration Testing
**Repository**: aws-dns-crossplane-poc (local development)
**Target Platform**: APE (Application Platform Engineering) IDP using Backstage + Crossplane + ArgoCD

---

## ⚠️ CRITICAL: Git Commit Policy

**ALWAYS commit as the user (arthur-bryan), NEVER as Claude.**

When making git commits in ANY repository (POC or APE repos):
- ✅ Commit author: `arthur-bryan <arthurbryan2030@gmail.com>`
- ❌ NO Claude attribution in commit messages
- ❌ NO "🤖 Generated with Claude Code" footer
- ❌ NO "Co-Authored-By: Claude <noreply@anthropic.com>" trailer

**This is NON-NEGOTIABLE.** We cannot and will not have Claude as a contributor/committer in the git history.

---

## CRITICAL: No Code Comments, No Emojis

**Do not write comments in code or YAML. Do not write emojis anywhere.**

Applies to every file Claude touches in any repo (lab/, prod templates, compositions, scripts, tests, configs):

- No inline `#`, `//`, `/* */`, or YAML `# ...` comments. Use clear identifiers and structure to convey intent.
- No emojis in code, YAML, JSON, shell, Python, scaffolder templates, commit messages, or anywhere committed to git.
- This file (.local/CLAUDE.md) is the only exception for prose/markdown documentation written for Claude itself.
- If existing comments or emojis are present in a file Claude is editing, leave them alone unless asked to clean up; don't add new ones.

**This is NON-NEGOTIABLE.** Self-documenting code only.

---

## 🎯 Project Overview

This project provides Crossplane-based DNS management compositions aligned with APE platform standards, enabling developers to self-service Route53 zones and records through Backstage templates.

### Key Features

- **Individual Resource Management**: Separate Zone and Record XRDs (no batch operations)
- **ALIAS Auto-Resolution**: Users select service types (CloudFront, ALB, etc.) without manual zone ID lookup
- **Weighted Routing**: Traffic distribution support via setIdentifier and weight fields
- **Immutability Constraints**: Zone names, record names, and types cannot be changed after creation
- **Editable Values**: Record values, TTL, and weights can be updated
- **APE Standard Compliance**: Follows patterns from ape-platform-charts (IAM, K8s, RDS, PostgreSQL)

---

## 🏗️ Architecture

### Resource Model

```
Domain (marketing)
  └─ SubDomain (websites)
       └─ System (corporate-site)
            └─ Environment (dev/hml/prd)
                 ├─ Zone (example.com)
                 └─ Record (www.example.com)
```

### Component Hierarchy

```
Backstage Template (User fills form)
         ↓
  Entity YAML committed to git
         ↓
  ArgoCD syncs to Kubernetes
         ↓
  Crossplane XR created
         ↓
  Composition renders MR
         ↓
  Provider-AWS creates Route53 resource
```

### AWS Account Mapping

- **dev** → AWS Account A (IRSA: irsa-dev-crossplane-route53)
- **hml** → AWS Account B (IRSA: irsa-hml-crossplane-route53)
- **prd** → AWS Account C (IRSA: irsa-prd-crossplane-route53)

---

## 📦 Components

### 1. Crossplane Compositions (`crossplane-compositions-dns/`)

Helm chart containing XRDs and compositions for DNS resources.

**Chart Structure**:
```
crossplane-compositions-dns/
├── Chart.yaml                    # Helm chart metadata (v0.1.0, appVersion 1.0.0)
├── values.yaml                   # Management policies configuration
└── templates/
    ├── crds/
    │   ├── zone.yaml             # zones.dock.tech XRD
    │   └── record.yaml           # records.dock.tech XRD
    └── compositions/
        ├── zone.yaml             # Zone composition (pipeline mode)
        └── record.yaml           # Record composition (ALIAS resolution + zone lookup)
```

#### XRD: Zone (zones.dock.tech)

**API Version**: v1
**Scope**: Namespaced
**Group**: dock.tech

**Fields**:
| Field | Type | Required | Immutable | Default | Description |
|-------|------|----------|-----------|---------|-------------|
| zoneName | string | Yes | Yes | - | Fully qualified domain name (e.g., example.com) |
| comment | string | No | No | - | Descriptive comment for the zone |
| tags | map[string]string | No | No | - | Custom tags for the zone |

**Validation**:
- `zoneName`: Must match pattern `^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$`
- `zoneName` is immutable after creation (enforced via x-kubernetes-validations)

**Status Fields**:
- `zoneId`: Route53 hosted zone ID (e.g., Z1234567890ABC)
- `nameServers`: Array of name servers for the zone

**Example**:
```yaml
apiVersion: dock.tech/v1
kind: Zone
metadata:
  name: example-com-zone
  namespace: system-corporate-site-dev
spec:
  zoneName: example.com
  comment: Corporate website DNS zone
```

#### XRD: Record (records.dock.tech)

**API Version**: v1
**Scope**: Namespaced
**Group**: dock.tech

**Fields**:
| Field | Type | Required | Immutable | Default | Description |
|-------|------|----------|-----------|---------|-------------|
| recordName | string | Yes | Yes | - | Record name (e.g., www.example.com) |
| type | enum | Yes | Yes | - | A, AAAA, CNAME, TXT, ALIAS |
| zoneId | string | No* | Yes | - | Route53 zone ID (if known) |
| zoneName | string | No* | Yes | - | Zone name for lookup (if zoneId not provided) |
| values | array[string] | No** | No | - | Record values (IPs, domains, text) |
| ttl | integer | No | No | 3600 | Time to live in seconds |
| setIdentifier | string | No | No | - | Unique ID for weighted routing |
| weight | integer | No | No | - | Weight (0-255) for traffic distribution |
| aliasTarget | object | No** | Partial | - | ALIAS target configuration |

\* Either `zoneId` or `zoneName` must be provided
\** Either `values` OR `aliasTarget` must be provided (not both)

**Alias Target Fields**:
| Field | Type | Required | Immutable | Description |
|-------|------|----------|-----------|-------------|
| serviceType | enum | No | Yes | CloudFront, ALB, NLB, S3Website, APIGateway, GlobalAccelerator, Custom |
| dnsName | string | Yes | No | Target DNS name |
| hostedZoneId | string | No | No | Custom zone ID (only if serviceType=Custom) |

**Type-Specific Validation**:
- **A**: Values must match IPv4 pattern `^([0-9]{1,3}\.){3}[0-9]{1,3}$`
- **AAAA**: Values must match IPv6 pattern
- **CNAME**: Single value, must be valid domain
- **TXT**: Values must be valid strings
- **ALIAS**: Must provide aliasTarget, no values field

**Immutability**:
- `recordName`, `type`, `serviceType` cannot be changed after creation
- `zoneId` and `zoneName` cannot be changed (prevents moving record between zones)
- `values`, `ttl`, `weight`, `dnsName` can be updated

**Example (Standard A Record)**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: www-example-com
  namespace: system-corporate-site-dev
spec:
  recordName: www.example.com
  type: A
  zoneName: example.com
  values:
    - 192.0.2.1
    - 192.0.2.2
  ttl: 300
```

**Example (ALIAS to CloudFront)**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: cdn-example-com
  namespace: system-corporate-site-dev
spec:
  recordName: cdn.example.com
  type: ALIAS
  zoneName: example.com
  aliasTarget:
    serviceType: CloudFront
    dnsName: d1234567890.cloudfront.net
```

**Example (Weighted Routing)**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: api-example-com-blue
  namespace: system-corporate-site-dev
spec:
  recordName: api.example.com
  type: A
  zoneName: example.com
  values:
    - 192.0.2.10
  setIdentifier: blue-deployment
  weight: 70
  ttl: 60
---
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: api-example-com-green
  namespace: system-corporate-site-dev
spec:
  recordName: api.example.com
  type: A
  zoneName: example.com
  values:
    - 192.0.2.20
  setIdentifier: green-deployment
  weight: 30
  ttl: 60
```

### 2. Backstage Templates (`backstage-templates/`)

Self-service forms for developers to create and edit DNS resources.

**Structure**:
```
backstage-templates/
├── README.md                        # Template documentation
├── shared/
│   └── entities/
│       ├── clone.yaml               # Clone ape-platform-entities repo
│       ├── commit.yaml              # Commit changes
│       ├── push.yaml                # Push to remote
│       ├── fetch-system.yaml        # Fetch system details from catalog
│       └── hierarchy-details.yaml   # Get domain/subdomain/env
└── templates/
    └── resources/
        └── aws/
            ├── zone.yaml            # Create zone template
            ├── record.yaml          # Create record template
            └── record-edit.yaml     # Edit record template (hidden)
```

#### Template: zone.yaml

**Purpose**: Create new Route53 hosted zones
**Access**: Visible in Backstage template catalog
**Operations**: Create-only (zones cannot be edited)

**Form Fields**:
1. **System** (EntityPicker) - Select target system from catalog
2. **Zone Name** (string) - FQDN with pattern validation
3. **Comment** (string, optional) - Descriptive comment
4. **Additional Tags** (array, optional) - Custom tags

**Process**:
1. User fills form → Backstage validates inputs
2. Clone ape-platform-entities repo
3. Fetch system details (domain, subdomain, environment)
4. Create entity YAML in `environments/{domain}/{subdomain}/{system}/{environment}/resources/aws/zone-{name}.yaml`
5. Commit with message: `feat(dns): create zone {zoneName}`
6. Push to remote → ArgoCD sync → Crossplane creates zone

**Generated Entity Example**:
```yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: zone-example-com
  namespace: system-corporate-site-dev
  annotations:
    dock.tech/scaffolder-parameters: '{"system":"corporate-site","zoneName":"example.com",...}'
spec:
  type: Zone
  lifecycle: production
  owner: group:platform-team
  system: corporate-site
  zoneName: example.com
  comment: Corporate website DNS zone
```

#### Template: record.yaml

**Purpose**: Create new DNS records
**Access**: Visible in Backstage template catalog
**Operations**: Create + Edit (values, TTL, weight editable)

**Form Fields**:
1. **System** (EntityPicker) - Select target system
2. **Zone** (EntityPicker) - Select existing zone from catalog (filters by system)
3. **Record Name** (string) - FQDN matching selected zone
4. **Type** (enum) - A, AAAA, CNAME, TXT, ALIAS
5. **Conditional Fields** (shown based on type):
   - **A/AAAA**: Values (array of IPs)
   - **CNAME**: Value (single domain)
   - **TXT**: Values (array of strings)
   - **ALIAS**: Service Type (enum) + DNS Name (string)
6. **TTL** (integer, default 3600) - Time to live
7. **Weighted Routing** (optional):
   - Set Identifier (string)
   - Weight (integer 0-255)

**Conditional Logic** (using JSON Schema dependencies):
```yaml
dependencies:
  type:
    oneOf:
      - properties:
          type:
            const: A
          values:
            title: IPv4 Addresses
            type: array
            items:
              type: string
              pattern: '^([0-9]{1,3}\.){3}[0-9]{1,3}$'
      - properties:
          type:
            const: ALIAS
          serviceType:
            title: AWS Service Type
            enum: [CloudFront, ALB, NLB, S3Website, APIGateway, GlobalAccelerator, Custom]
          dnsName:
            title: Target DNS Name
            type: string
```

**Process**:
1. User fills form → Backstage shows/hides fields based on type
2. Clone ape-platform-entities repo
3. Fetch zone details (zoneId) from selected entity
4. Create entity YAML with embedded XR spec
5. Commit with message: `feat(dns): create record {recordName}`
6. Push → ArgoCD → Crossplane → Route53

**Generated Entity Example**:
```yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: record-www-example-com
  namespace: system-corporate-site-dev
  annotations:
    dock.tech/scaffolder-parameters: '{"zone":"zone-example-com","recordName":"www.example.com",...}'
spec:
  type: Record
  lifecycle: production
  owner: group:platform-team
  system: corporate-site
  dependsOn:
    - resource:zone-example-com
  recordName: www.example.com
  recordType: A
  values:
    - 192.0.2.1
  ttl: 300
```

#### Template: record-edit.yaml

**Purpose**: Edit existing DNS records
**Access**: Hidden from catalog (tagged with `hidden`)
**Operations**: Update values, TTL, weight only

**Key Differences from record.yaml**:
1. **Pre-filled Fields**: Reads from `dock.tech/scaffolder-parameters` annotation
2. **Disabled Fields**: recordName, type, serviceType (immutable)
3. **Merge Action**: Uses `roadiehq:utils:merge` instead of `fs:write` (preserves structure)
4. **No Zone Picker**: Zone cannot be changed

**Process**:
1. Developer clicks "Edit" on existing record entity in Backstage catalog
2. Backstage loads record-edit template with pre-filled values
3. User modifies editable fields (values, TTL, weight)
4. Template merges changes into existing entity YAML
5. Commit with message: `chore(dns): update record {recordName}`
6. Push → ArgoCD detects change → Crossplane updates Route53

**Form Behavior**:
```yaml
parameters:
  - properties:
      recordName:
        ui:disabled: true     # Cannot change
        default: ${{ entity.spec.recordName }}
      type:
        ui:disabled: true     # Cannot change
        default: ${{ entity.spec.recordType }}
      values:
        # Editable
        default: ${{ entity.spec.values }}
      ttl:
        # Editable
        default: ${{ entity.spec.ttl }}
```

### 3. Composition Logic

#### Zone Composition (zone.yaml)

**Mode**: Pipeline
**Functions**: function-go-templating, function-auto-ready

**Process**:
1. Extract hierarchy annotations (domain, subdomain, system, environment)
2. Determine AWS account based on environment (dev/hml/prd)
3. Render Route53 Zone managed resource with:
   - providerConfigRef: `{accountName}` (IRSA-based)
   - forProvider.comment: User comment
   - forProvider.tags: domain, subdomain, system, environment
4. Auto-ready function marks composite as ready when MR is ready
5. Patch zoneId and nameServers to status

**Key Code** (simplified):
```yaml
apiVersion: route53.aws.upbound.io/v1beta1
kind: Zone
spec:
  providerConfigRef:
    name: {{ $accountName }}  # aws-dev, aws-hml, or aws-prd
  forProvider:
    comment: {{ $comment }}
    tags:
      domain: {{ $domain }}
      subdomain: {{ $subdomain }}
      system: {{ $system }}
      environment: {{ $environment }}
  managementPolicies:
    - Observe
    - Create
    - Delete
    # Note: Update intentionally excluded (zones are create-only)
```

#### Record Composition (record.yaml)

**Mode**: Pipeline
**Functions**: function-go-templating, function-auto-ready

**Complex Logic**:
1. **Zone Lookup**: If zoneName provided, lookup zoneId via observeOnly Zone resource
2. **ALIAS Resolution**: If type=ALIAS, resolve hostedZoneId from serviceType + region:
   - CloudFront → Z2FDTNDATAQYW2 (global)
   - ALB → Regional mapping (70+ entries)
   - NLB → Regional mapping
   - S3Website → Regional mapping
   - APIGateway → Regional mapping
   - GlobalAccelerator → Z2BJ6VIGRCS5A4 (global)
   - Custom → Use user-provided hostedZoneId
3. **Weighted Routing**: If setIdentifier provided, enable weighted routing policy
4. Render Route53 Record managed resource
5. Auto-ready function marks ready

**ALIAS Zone ID Mappings** (excerpt):
```yaml
{{- $resolvedAliasZoneId := "" }}
{{- if and (eq $type "ALIAS") $aliasTarget }}
  {{- $serviceType := $aliasTarget.serviceType }}
  {{- if eq $serviceType "CloudFront" }}
    {{- $resolvedAliasZoneId = "Z2FDTNDATAQYW2" }}
  {{- else if eq $serviceType "ALB" }}
    {{- if eq $region "us-east-1" }}{{- $resolvedAliasZoneId = "Z35SXDOTRQ7X7K" }}
    {{- else if eq $region "us-east-2" }}{{- $resolvedAliasZoneId = "Z3AADJGX6KTTL2" }}
    {{- else if eq $region "us-west-1" }}{{- $resolvedAliasZoneId = "Z368ELLRRE2KJ0" }}
    # ... 70+ total mappings
  {{- end }}
{{- end }}
```

**Managed Resource** (simplified):
```yaml
apiVersion: route53.aws.upbound.io/v1beta1
kind: Record
spec:
  providerConfigRef:
    name: {{ $accountName }}
  forProvider:
    name: {{ $recordName }}
    type: {{ if eq $type "ALIAS" }}A{{ else }}{{ $type }}{{ end }}
    zoneId: {{ $zoneId }}
    {{- if ne $type "ALIAS" }}
    records: {{ $values }}
    ttl: {{ $ttl }}
    {{- end }}
    {{- if eq $type "ALIAS" }}
    alias:
      - name: {{ $aliasTarget.dnsName }}
        zoneId: {{ $resolvedAliasZoneId }}
        evaluateTargetHealth: false
    {{- end }}
    {{- if $setIdentifier }}
    setIdentifier: {{ $setIdentifier }}
    weightedRoutingPolicy:
      - weight: {{ $weight }}
    {{- end }}
  managementPolicies:
    - Observe
    - Create
    - Update
    - Delete
```

---

## 🔄 APE Platform Standards Compliance

### 1. Naming Conventions ✅

**Standard**: Simple resource names (Role, EKS, Bucket, Zone, Record)
**Compliance**: NOT Route53Zone, NOT DNSZone, NOT Route53Record

**Examples from ape-platform-charts**:
- IAM: Role, Policy
- K8s: EKS, NodeGroup
- Database: RDS, PostgreSQL
- **DNS**: Zone, Record ← our implementation

### 2. API Group ✅

**Standard**: All XRDs use `dock.tech` API group
**Compliance**:
- zones.dock.tech
- records.dock.tech

### 3. Scope ✅

**Standard**: Namespaced resources (not cluster-scoped)
**Compliance**: All XRDs use `scope: Namespaced`

### 4. Composition Mode ✅

**Standard**: Pipeline mode with go-templating + auto-ready
**Compliance**: All compositions use:
```yaml
mode: Pipeline
pipeline:
  - step: render-resources
    functionRef:
      name: crossplane-contrib-function-go-templating
  - step: auto-ready
    functionRef:
      name: crossplane-contrib-function-auto-ready
```

### 5. Backstage Template Structure ✅

**Standard**: Use shared partials via $yaml, EntityPicker for relationships, store parameters in annotations
**Compliance**:
- Shared partials: clone.yaml, commit.yaml, push.yaml, fetch-system.yaml
- EntityPicker used for System and Zone selection
- Parameters stored in `dock.tech/scaffolder-parameters` annotation

### 6. Chart Structure ✅

**Standard**: charts/crossplane-compositions-{domain}/ with templates/crds/ and templates/compositions/
**Compliance**:
```
crossplane-compositions-dns/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── crds/
    │   ├── zone.yaml
    │   └── record.yaml
    └── compositions/
        ├── zone.yaml
        └── record.yaml
```

### 7. No Functions in Charts ✅

**Standard**: Crossplane functions are cluster-wide, not included in composition charts
**Compliance**: Removed `crossplane-functions/` folder, rely on cluster-installed functions

### 8. Documentation Language ✅

**Standard**: Portuguese for internal documentation
**Compliance**: crossplane-compositions-dns/README.md written in Portuguese

---

## 🚀 Development Workflow

### Local Development (Current Branch: feature/ape-platform-alignment)

```bash
# 1. Navigate to project
cd /home/bryan/github/aws-dns-crossplane-poc

# 2. Make changes to compositions
vim crossplane-compositions-dns/templates/crds/zone.yaml

# 3. Test locally (if k3d cluster available)
helm template crossplane-compositions-dns/ | kubectl apply -f -

# 4. Commit with descriptive message
git add .
git commit -m "feat(dns): add new field to Zone XRD"

# 5. Push to feature branch
git push origin feature/ape-platform-alignment
```

### Integration with APE Platform

```bash
# 1. Copy compositions to ape-platform-charts (when ready)
cp -r crossplane-compositions-dns/ ../ape-platform-charts/charts/

# 2. Copy templates to ape-platform-backstage-templates
cp -r backstage-templates/templates/resources/aws/ \
   ../ape-platform-backstage-templates/templates/resources/

cp -r backstage-templates/shared/ \
   ../ape-platform-backstage-templates/shared/

# 3. Commit to respective repos (admin will do this)
# 4. ArgoCD will sync changes to cluster
# 5. Backstage will show new templates in catalog
```

---

## 📊 Usage Examples

### Example 1: Create Simple Zone

**Backstage Form**:
- System: corporate-site
- Zone Name: example.com
- Comment: Corporate website zone

**Generated Entity**:
```yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: zone-example-com
  namespace: system-corporate-site-dev
spec:
  type: Zone
  zoneName: example.com
  comment: Corporate website zone
```

**Crossplane XR Created**:
```yaml
apiVersion: dock.tech/v1
kind: Zone
metadata:
  name: zone-example-com
  namespace: system-corporate-site-dev
spec:
  zoneName: example.com
  comment: Corporate website zone
status:
  zoneId: Z1234567890ABC
  nameServers:
    - ns-123.awsdns-12.com
    - ns-456.awsdns-45.net
```

### Example 2: Create A Record

**Backstage Form**:
- System: corporate-site
- Zone: zone-example-com
- Record Name: www.example.com
- Type: A
- Values: ["192.0.2.1", "192.0.2.2"]
- TTL: 300

**Generated XR**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: record-www-example-com
  namespace: system-corporate-site-dev
spec:
  recordName: www.example.com
  type: A
  zoneName: example.com
  values:
    - 192.0.2.1
    - 192.0.2.2
  ttl: 300
```

### Example 3: Create ALIAS to CloudFront

**Backstage Form**:
- System: corporate-site
- Zone: zone-example-com
- Record Name: cdn.example.com
- Type: ALIAS
- Service Type: CloudFront
- DNS Name: d1234567890.cloudfront.net

**Generated XR**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: record-cdn-example-com
  namespace: system-corporate-site-dev
spec:
  recordName: cdn.example.com
  type: ALIAS
  zoneName: example.com
  aliasTarget:
    serviceType: CloudFront
    dnsName: d1234567890.cloudfront.net
```

**Route53 Result**: Record created with hostedZoneId automatically resolved to Z2FDTNDATAQYW2

### Example 4: Weighted Routing (Blue/Green)

**Two Records**:

**Blue (70% traffic)**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: record-api-example-com-blue
spec:
  recordName: api.example.com
  type: A
  zoneName: example.com
  values: ["192.0.2.10"]
  setIdentifier: blue-deployment
  weight: 70
  ttl: 60
```

**Green (30% traffic)**:
```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: record-api-example-com-green
spec:
  recordName: api.example.com
  type: A
  zoneName: example.com
  values: ["192.0.2.20"]
  setIdentifier: green-deployment
  weight: 30
  ttl: 60
```

**Result**: DNS queries to api.example.com return 192.0.2.10 ~70% of the time, 192.0.2.20 ~30%

### Example 5: Update Record Values

**Current Record**:
```yaml
spec:
  recordName: www.example.com
  type: A
  values: ["192.0.2.1"]
  ttl: 300
```

**Update Process**:
1. Developer clicks "Edit" on www-example-com entity in Backstage
2. record-edit template loads with pre-filled values
3. Developer changes values to ["192.0.2.5", "192.0.2.6"]
4. Developer changes TTL to 600
5. Clicks "Create" → Git commit → ArgoCD sync → Route53 updated

**Updated Record**:
```yaml
spec:
  recordName: www.example.com  # Immutable
  type: A                       # Immutable
  values: ["192.0.2.5", "192.0.2.6"]  # Updated
  ttl: 600                      # Updated
```

---

## 🔧 Troubleshooting

### Issue: Zone creation fails with "Zone already exists"

**Cause**: Route53 does not allow duplicate zone names in same account
**Solution**: Check if zone exists via AWS Console, use import if needed

### Issue: Record shows "Cannot find zone"

**Cause**: zoneName lookup failed (zone doesn't exist or wrong namespace)
**Solution**: Verify zone exists in same namespace, use zoneId directly if known

### Issue: ALIAS record fails with "Invalid zone ID"

**Cause**: Service type + region combination not mapped
**Solution**: Use serviceType=Custom and provide hostedZoneId manually

### Issue: Cannot update recordName

**Cause**: recordName is immutable by design
**Solution**: Delete old record, create new one with different name

### Issue: Weighted routing not working

**Cause**: setIdentifier missing or weights don't sum properly
**Solution**: Ensure all weighted records have unique setIdentifier and weight ≥ 0

### Issue: Changes not appearing in Route53

**Cause**: ArgoCD not syncing or Crossplane provider issue
**Check**:
```bash
# Check XR status
kubectl get zones.dock.tech -n system-corporate-site-dev
kubectl describe zone zone-example-com -n system-corporate-site-dev

# Check managed resource
kubectl get zone.route53.aws.upbound.io
kubectl describe zone.route53.aws.upbound.io <name>

# Check provider logs
kubectl logs -n crossplane-system -l pkg.crossplane.io/provider=provider-aws-route53
```

---

## 🔐 Security

### IRSA (IAM Roles for Service Accounts)

Each environment uses dedicated IRSA roles:

- **dev**: `irsa-dev-crossplane-route53`
- **hml**: `irsa-hml-crossplane-route53`
- **prd**: `irsa-prd-crossplane-route53`

**IAM Policy** (Route53-specific permissions):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "route53:CreateHostedZone",
        "route53:DeleteHostedZone",
        "route53:GetHostedZone",
        "route53:ListHostedZones",
        "route53:UpdateHostedZoneComment",
        "route53:ChangeResourceRecordSets",
        "route53:GetChange",
        "route53:ListResourceRecordSets",
        "route53:ListTagsForResource",
        "route53:ChangeTagsForResource"
      ],
      "Resource": "*"
    }
  ]
}
```

**ProviderConfig** (per environment):
```yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: aws-dev
spec:
  credentials:
    source: IRSA
```

---

## 📈 Monitoring

### Key Metrics

**Crossplane Level**:
- Composition reconciliation duration
- Managed resource sync status
- Provider health

**Route53 Level**:
- Zone count per environment
- Record count per zone
- DNS query count (CloudWatch)

### Logging

**Check Crossplane Logs**:
```bash
# Provider logs
kubectl logs -n crossplane-system -l pkg.crossplane.io/provider=provider-aws-route53 --tail=100

# Function logs
kubectl logs -n crossplane-system -l pkg.crossplane.io/function=function-go-templating --tail=100
```

**Check ArgoCD Sync Status**:
```bash
# Via CLI
argocd app list | grep dns

# Via UI
# Navigate to ArgoCD dashboard → Applications → filter by "dns"
```

---

## ✅ Best Practices

### 1. Zone Naming
- Use lowercase only
- Use hyphens (not underscores)
- Match domain structure (example-dev.com for dev, example.com for prod)

### 2. Record Management
- Use TTL 60-300 for frequently changing records (blue/green)
- Use TTL 3600+ for stable records
- Always provide setIdentifier for weighted records
- Keep record names fully qualified (www.example.com, not just www)

### 3. ALIAS Records
- Prefer ALIAS over CNAME at zone apex (example.com)
- Use CloudFront ALIAS for CDN distributions
- Use ALB ALIAS for load balancers in same region
- Verify dnsName ends with correct AWS domain suffix

### 4. Immutability
- Plan record names carefully (cannot rename)
- Choose record type correctly (cannot change A → CNAME)
- Use delete+recreate for identity changes

### 5. Weighted Routing
- Use descriptive setIdentifiers (blue-deployment, green-deployment)
- Ensure weights sum to intended distribution
- Update weights gradually for traffic shifting
- Monitor DNS propagation (TTL-dependent)

### 6. GitOps
- Never edit resources directly in Kubernetes
- Always use Backstage templates or Git commits
- Keep entity YAML in ape-platform-entities repo
- Use descriptive commit messages (feat, chore, fix)

---

## 🗂️ Repository Structure

```
aws-dns-crossplane-poc/
├── .git/                                    # Git repository
├── .gitignore                               # Ignore patterns
├── .local/
│   └── CLAUDE.md                           # This file (project context)
├── crossplane-compositions-dns/             # Helm chart (compositions + XRDs)
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── README.md                           # Portuguese documentation
│   └── templates/
│       ├── crds/
│       │   ├── zone.yaml                   # zones.dock.tech XRD
│       │   └── record.yaml                 # records.dock.tech XRD
│       └── compositions/
│           ├── zone.yaml                   # Zone composition
│           └── record.yaml                 # Record composition (ALIAS + lookup)
├── backstage-templates/                     # Self-service templates
│   ├── README.md                           # Template documentation
│   ├── shared/
│   │   └── entities/
│   │       ├── clone.yaml
│   │       ├── commit.yaml
│   │       ├── push.yaml
│   │       ├── fetch-system.yaml
│   │       └── hierarchy-details.yaml
│   └── templates/
│       └── resources/
│           └── aws/
│               ├── zone.yaml               # Create zone template
│               ├── record.yaml             # Create record template
│               └── record-edit.yaml        # Edit record template (hidden)
├── crossplane-provider-config-aws/         # IRSA provider configs
│   ├── Chart.yaml
│   └── values.yaml
└── crossplane-providers/                    # Provider installations
    ├── Chart.yaml
    └── values.yaml
```

---

## 📝 Change Log

### 2025-04-21 - APE Platform Alignment Complete

**Major Changes**:
1. **Renamed Resources**: DNSZone → Zone, DNSRequest → Record
2. **Removed Batch Operations**: Individual resource management only
3. **Added ALIAS Auto-Resolution**: 70+ AWS service zone ID mappings
4. **Added Weighted Routing**: setIdentifier + weight support
5. **Implemented Immutability**: recordName, type, serviceType cannot change
6. **Created Backstage Templates**: zone.yaml, record.yaml, record-edit.yaml
7. **Removed Region from Zone**: Route53 is global service
8. **Changed Default TTL**: 300 → 3600 seconds
9. **Updated Chart Version**: appVersion 1.16.0 → 1.0.0
10. **Removed Tests Folder**: Per project standards
11. **Removed crossplane-functions/**: Functions are cluster-wide
12. **Created Portuguese README**: APE platform documentation standard

**Compliance Achieved**:
- ✅ Simple resource names (Zone, Record)
- ✅ API group: dock.tech
- ✅ Scope: Namespaced
- ✅ Pipeline mode with go-templating
- ✅ Backstage template structure
- ✅ No functions in charts
- ✅ Portuguese documentation

**Previous POC Artifacts Removed**:
- applications/dns-dashboard/
- docs/
- examples/
- gitops/
- platform/
- scripts/
- requirements.txt
- config.env.example

---

## 🎯 Next Steps

### Integration Testing
1. [ ] Test zone creation via Backstage template
2. [ ] Test record creation (all types: A, AAAA, CNAME, TXT, ALIAS)
3. [ ] Test record editing (values, TTL, weight)
4. [ ] Test weighted routing with traffic shifting
5. [ ] Verify ALIAS auto-resolution for CloudFront, ALB, NLB
6. [ ] Test zone deletion (verify no orphaned records)

### Platform Integration
1. [ ] Copy compositions to ape-platform-charts repo
2. [ ] Copy templates to ape-platform-backstage-templates repo
3. [ ] Update ArgoCD application definitions
4. [ ] Configure IRSA roles for all environments (dev, hml, prd)
5. [ ] Test end-to-end flow (Backstage → Git → ArgoCD → Crossplane → Route53)

### Production Readiness
1. [ ] Add zone deletion protection (prevent deletion with existing records)
2. [ ] Implement record set awareness (warn when deleting weighted record)
3. [ ] Add metrics and monitoring dashboards
4. [ ] Create runbook for common operations
5. [ ] Document rollback procedures
6. [ ] Add integration tests for compositions
7. [ ] Set up alerts for composition failures

---

## 📚 References

### APE Platform Documentation
- `/home/bryan/github/ape-backstage-docs/docs/platform-architecture-workflow.md`
- `/home/bryan/github/ape-backstage-docs/docs/start-guide-new-composition.md`

### APE Platform Repositories
- **ape-platform-charts**: Reference implementations (IAM, K8s, RDS, PostgreSQL)
- **ape-platform-backstage-templates**: Template patterns and shared partials
- **ape-platform-entities**: GitOps source of truth (entity YAML files)
- **ape-platform-k8s-addons**: ArgoCD application definitions

### AWS Documentation
- Route53 Developer Guide: https://docs.aws.amazon.com/route53/
- ALIAS Record Types: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html
- Weighted Routing: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-weighted.html

### Crossplane Documentation
- XRD API v2: https://docs.crossplane.io/latest/concepts/composite-resource-definitions/
- Composition Functions: https://docs.crossplane.io/latest/concepts/composition-functions/
- Pipeline Mode: https://docs.crossplane.io/latest/concepts/compositions/#pipeline-mode

---

## 🤝 Contributing

This project follows APE platform standards. When making changes:

1. **Read APE documentation first** - Don't assume patterns
2. **Study reference implementations** - Check ape-platform-charts for examples
3. **Test locally before committing** - Use helm template + kubectl apply
4. **Use descriptive commit messages** - Follow conventional commits (feat, fix, chore)
5. **Document in Portuguese** - APE platform standard for internal docs
6. **Validate XRD ↔ Template contract** - Ensure field names match exactly

---

**Project Status**: APE Platform Alignment Complete ✅
**Last Updated**: 2025-04-21
**Branch**: feature/ape-platform-alignment
**Ready For**: Integration Testing → Platform Integration → Production Deployment
