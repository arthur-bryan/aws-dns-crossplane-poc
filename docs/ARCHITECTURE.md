# DNS Automation Architecture - Dual-Frontend Design

## Overview

This architecture enables two distinct frontends to manage DNS infrastructure through Crossplane + ArgoCD, replacing the legacy Terraform + Atlantis approach. Each frontend has different workflows and approval mechanisms.

## Core Principle

The system provides TWO INDEPENDENT paths to DNS provisioning:

1. **IDP Frontend**: Direct DNSRequest XRD creation for platform apps (no approvals, self-service)
2. **Slack Frontend**: Legacy workflow through infra-dns-api (keeps ALL existing approval/freeze/window logic)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND LAYER                                  │
├──────────────────────────────────┬──────────────────────────────────────┤
│   Frontend 1: IDP Apps           │   Frontend 2: Legacy Apps            │
│   (Kubernetes-Native)             │   (Slack Bot)                        │
│                                   │                                      │
│   Developer commits manifest      │   Slack: /dns create ...             │
│         ↓                         │         ↓                            │
│   ArgoCD syncs DNSRequest XRD     │   dns-lambda-trigger                 │
│         ↓                         │         ↓                            │
│   Crossplane provisions           │   infra-dns-api REST API             │
│   (NO approvals, direct deploy)   │   (Approvals, Freeze, Window, SQS,   │
│                                   │    Step Functions, DynamoDB)         │
│                                   │         ↓                            │
│                                   │   deployment_executor_yaml           │
│                                   │   (Generate DNSRequest YAML)         │
│                                   │         ↓                            │
│                                   │   GitHub PR with YAML file           │
│                                   │         ↓                            │
│                                   │   ArgoCD syncs to cluster            │
│                                   │         ↓                            │
│                                   │   Crossplane provisions              │
└──────────────────────────────────┴──────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     CROSSPLANE COMPOSITION LAYER                         │
│                                                                          │
│   DNSRequest XRD → Composition → XDNSZone / XDNSRecord                  │
└─────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS PROVIDER LAYER                                │
│                                                                          │
│   Route53 HostedZone + ResourceRecordSet (Multi-Account via IRSA)       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### Frontend Layer

#### Frontend 1: IDP Apps (Kubernetes-Native)

Apps managed by the Internal Developer Platform declare DNS requirements as Kubernetes Custom Resources.

```yaml
apiVersion: dns.infra.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: req-app-dns
  namespace: myapp
spec:
  requesterName: dev-team@dock.tech
  action: create_record
  env: dev
  hostedzone: myapp.dev.dock.tech
  businessUnit: banking
  originTicket: https://jira.dock.tech/browse/INFRA-1234
  records:
    - name: api
      type: A
      value: "10.0.1.100"
      ttl: "300"
```

**Workflow**:
1. Developer commits DNSRequest manifest to app repository
2. ArgoCD detects change and syncs to cluster
3. Crossplane immediately provisions resources (NO approval controller)
4. IDP platform manages deployment controls (freeze, windows, etc.)

**Key Points**:
- NO approval controller (IDP handles that at platform level)
- NO integration with infra-dns-api
- Direct Crossplane provisioning
- IDP responsible for its own governance

#### Frontend 2: Legacy Apps (Slack Bot)

Apps not on IDP platform continue using the existing Slack bot workflow with ALL existing governance.

**Workflow**:
1. User sends Slack command: `/dns create record api.myapp.hml.dock.tech A 10.0.2.50`
2. dns-lambda-trigger validates and transforms to API payload
3. Calls infra-dns-api REST endpoint
4. infra-dns-api workflow:
   - Stores request in DynamoDB
   - Starts Step Functions state machine
   - Infrastructure approval (manual or auto)
   - Security approval (if required for env + public records)
   - Validates deployment conditions (freeze period, deployment window)
   - Enqueues to SQS FIFO (per-zone serialization)
5. deployment_executor_yaml processes queue:
   - Generates DNSRequest XRD YAML
   - Creates GitHub PR with YAML file
   - Monitors ArgoCD sync status
   - Updates DynamoDB request status
6. ArgoCD syncs PR to cluster
7. Crossplane provisions Route53 resources
8. Status updates flow back to Slack

**Key Points**:
- KEEPS ALL existing infra-dns-api logic (approvals, freeze, window, SQS, Step Functions, DynamoDB)
- ONLY REPLACES deployment executor (Terraform → YAML, Atlantis → ArgoCD)
- NO approval controller in Kubernetes (approvals managed by infra-dns-api)
- NO bridge service (deployment_executor_yaml is Python module for infra-dns-api)

### Deployment Executor YAML Module

Python module for integration into infra-dns-api deployment_executor Lambda.

**Location**: `/deployment_executor_yaml/` (in this POC repo)

**Components**:
- `yaml_generator.py`: Transform API request data to DNSRequest XRD YAML
- `argocd_client.py`: Monitor ArgoCD sync status (replaces Atlantis webhook parsing)
- `git_operations.py`: Create GitHub PRs with YAML files
- `models.py`: Pydantic models for validation

**Integration Point**:
```python
# In infra-dns-api src/deployment_executor/handler.py
from deployment_executor_yaml import generate_dnsrequest_yaml, create_yaml_pr, ArgoCDClient

def execute_deployment(request_data):
    # Generate YAML (replaces HCL generation)
    yaml_content = generate_dnsrequest_yaml(request_data)

    # Create PR (replaces Terraform PR)
    pr_info = create_yaml_pr(
        request_id=request_data['id'],
        env=request_data['env'],
        action=request_data['action'],
        zone=request_data['hostedzone'],
        yaml_content=yaml_content,
        github_token=os.environ['GITHUB_TOKEN'],
        repo_name='dock-tech/dns-infrastructure',
        requester_name=request_data['requester_name'],
        origin_ticket=request_data['origin_ticket']
    )

    # Monitor ArgoCD (replaces Atlantis webhook)
    argocd = ArgoCDClient(
        api_url=os.environ['ARGOCD_URL'],
        token=os.environ['ARGOCD_TOKEN']
    )
    success, status = argocd.wait_for_sync('dns-infrastructure', timeout=600)

    # Update DynamoDB status
    if success:
        update_request_status(request_data['id'], 'deployed')
    else:
        update_request_status(request_data['id'], 'failed')
```

### Crossplane Composition Layer

#### DNSRequest XRD (Composite Resource)

Unified data model matching infra-dns-api schema:
- All record types: A, CNAME, TXT, ALIAS
- Weighted routing support
- UPDATE operations with old_value/new_value
- Approval tracking fields (for audit only, NOT enforced)
- Rollback metadata

Composes to:
- XDNSZone (for create_hosted_zone actions)
- XDNSRecord (for record operations)

### AWS Provider Layer

Crossplane AWS Provider manages Route53 resources:
- HostedZone (route53.aws.crossplane.io/v1alpha1)
- ResourceRecordSet (route53.aws.crossplane.io/v1alpha1)

Multi-account support via ProviderConfig:
- aws-dev (dnszone-dev account)
- aws-hml (dnszone-hml account)
- aws-prd (dnszone-prd account)

## Data Flow Comparison

### IDP App Flow (Direct)

```
Developer commits DNSRequest manifest
    ↓
ArgoCD syncs to cluster
    ↓
Crossplane Composition creates managed resources
    ↓
AWS Provider provisions Route53 records
    ↓
Status updates propagate to DNSRequest.status
```

**Duration**: 30-90 seconds (no approvals)

### Legacy App Flow (Full Workflow)

```
Slack command
    ↓
dns-lambda-trigger (validation)
    ↓
infra-dns-api REST API (create request in DynamoDB)
    ↓
Step Functions (approval workflow state machine)
    ↓ [wait for infrastructure approval]
Infrastructure approval (manual or auto-approved for cert validation)
    ↓ [if required: wait for security approval]
Security approval (manual, if env=prd OR env=hml+public records)
    ↓
ValidateDeploymentConditions Lambda
    ↓ [defer if in freeze period or outside deployment window]
Wait for freeze to end / deployment window to open
    ↓
Enqueue to SQS FIFO (MessageGroupId = env:zone)
    ↓
deployment_executor_yaml Lambda polls SQS
    ↓
Generate DNSRequest XRD YAML
    ↓
Create GitHub PR with YAML file (dns-requests/env/request_id.yaml)
    ↓
ArgoCD detects PR merge
    ↓
ArgoCD syncs DNSRequest to cluster
    ↓
Crossplane provisions Route53 resources
    ↓
ArgoCD reports sync status
    ↓
deployment_executor_yaml checks ArgoCD API
    ↓
Send Step Functions callback (task token)
    ↓
Update DynamoDB request status = deployed
    ↓
Publish EventBridge event
    ↓
Response to Slack
```

**Duration**: Minutes to days (depends on approvals)

## Design Decisions

### Decision 1: NO Approval Controller

**Choice**: Approvals managed by infra-dns-api (for Slack frontend), NOT by Kubernetes operator.

**Rationale**:
- IDP apps do NOT need approvals (self-service platform)
- Legacy apps KEEP existing approval workflow in infra-dns-api (Step Functions)
- Adding approval controller would duplicate logic and create conflicts
- Separation of concerns: infra-dns-api = governance, Crossplane = provisioning

### Decision 2: NO Bridge Service

**Choice**: deployment_executor_yaml is Python module for infra-dns-api, NOT standalone service.

**Rationale**:
- infra-dns-api already has deployment executor Lambda
- Module can be imported and used directly in Lambda
- No need for HTTP bridge (adds latency and complexity)
- Maintains existing architecture pattern

### Decision 3: YAML-Based GitOps

**Choice**: Generate DNSRequest YAML files instead of Terraform HCL.

**Rationale**:
- Crossplane is Kubernetes-native, expects YAML manifests
- ArgoCD syncs YAML from Git (same GitOps pattern as Terraform)
- One-to-one mapping: request ID → YAML file
- Easier to debug (kubectl describe dnsrequest)

### Decision 4: ArgoCD Status Checking

**Choice**: Poll ArgoCD API instead of webhook callbacks.

**Rationale**:
- Atlantis used webhooks for "plan complete" and "apply complete"
- ArgoCD has REST API for sync status and resource health
- Polling simpler than webhook endpoint + authentication
- Can wait synchronously in Lambda (max 15 min timeout)

### Decision 5: Git Repository Structure

**Choice**: Separate directory per environment for YAML files.

**Structure**:
```
dns-infrastructure/
├── dns-requests/
│   ├── dev/
│   │   ├── req-a3f9b2c1.yaml
│   │   └── req-xyz789.yaml
│   ├── hml/
│   │   └── req-def456.yaml
│   └── prd/
│       └── req-abc123.yaml
```

**Rationale**:
- Environment isolation (same as Terraform dnszones-{env}/)
- ArgoCD can sync per-environment or all at once
- Easy to audit: one file = one request
- Git history tracks all changes

## Migration Strategy

### Phase 1: Deploy Crossplane Infrastructure
- Install Crossplane + AWS Provider in Kubernetes cluster
- Deploy DNSRequest XRD and compositions
- Configure ProviderConfigs for multi-account access
- Deploy ArgoCD with dns-infrastructure application

### Phase 2: IDP Adoption (Parallel with Terraform)
- IDP platform apps start using DNSRequest XRD directly
- Terraform infrastructure remains operational for legacy apps
- NO changes to infra-dns-api yet

### Phase 3: Integrate deployment_executor_yaml
- Add deployment_executor_yaml module to infra-dns-api codebase
- Update deployment_executor Lambda to use YAML generation
- Configure GitHub repo and ArgoCD credentials
- Test with dev environment requests

### Phase 4: Cutover Legacy Apps
- Enable YAML path in infra-dns-api for hml environment
- Monitor side-by-side with Terraform (both active)
- Cutover prd environment after validation
- Decommission Atlantis

### Phase 5: Migrate Existing Zones
- Export Terraform state to Crossplane manifests
- Gradually import existing zones into Crossplane management
- Complete decommission of Terraform

## Operational Considerations

### Approval Workflow (Legacy Frontend Only)

Approvals managed by infra-dns-api via Step Functions:

**Infrastructure Approval**:
```bash
curl -X POST "${API_URL}/requests/{id}/approvals/infrastructure" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{
    "approver_name": "john.doe@dock.tech"
  }'
```

**Security Approval**:
```bash
curl -X POST "${API_URL}/requests/{id}/approvals/security" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{
    "approver_name": "security@dock.tech"
  }'
```

IDP apps bypass approvals entirely (self-service).

### Monitoring

**Key Metrics**:
- DNSRequest creation rate (per frontend)
- Approval latency (Slack frontend only)
- ArgoCD sync success rate
- Crossplane reconciliation time
- Route53 API call rate

**Dashboards**:
- Grafana: Crossplane provider metrics
- ArgoCD UI: Application sync status
- CloudWatch: infra-dns-api Lambda metrics

### Rollback

Rollback initiated via infra-dns-api (Slack frontend):
```bash
curl -X POST "${API_URL}/requests/{original_id}/rollbacks" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{
    "requester_name": "user@dock.tech",
    "reason": "Record causes DNS resolution failures"
  }'
```

Creates NEW DNSRequest with rollback action, goes through same approval workflow.

IDP apps rollback via Git revert (standard GitOps practice).

## Security

### RBAC

**IDP Apps**:
- ServiceAccount per namespace with limited DNSRequest creation
- No cluster-wide permissions

**deployment_executor_yaml Lambda**:
- ServiceAccount with DNSRequest create/update permissions
- Scoped to dns-infrastructure namespace

**No Approval Controller**:
- Not deployed (approvals in infra-dns-api)

### AWS IAM

ProviderConfig uses IRSA (IAM Roles for Service Accounts):
- Crossplane pod assumes environment-specific role
- Roles have least-privilege Route53 permissions
- Cross-account via trust relationships

### Audit Trail

**Slack Frontend**:
- DynamoDB: Full request history with approvals, timestamps
- EventBridge: All state transitions
- GitHub: PR history for YAML changes
- Kubernetes: DNSRequest resource history

**IDP Frontend**:
- Git: Commit history of DNSRequest manifests
- Kubernetes: Resource audit logs
- ArgoCD: Sync history

## Performance

**Expected Throughput**:
- IDP apps: 100+ requests/min (direct Crossplane provisioning)
- Slack frontend: 10-20 requests/min (approval bottleneck)
- Crossplane reconciliation: 30-60s per resource
- End-to-end IDP: 1-2 minutes
- End-to-end Slack (approved): 3-5 minutes

## High Availability

- Crossplane: Single replica with pod restart on failure
- ArgoCD: HA deployment with 3 replicas
- infra-dns-api: Multi-region Lambda (existing HA)
- deployment_executor_yaml: Lambda with SQS FIFO (existing HA)

## Disaster Recovery

- DNSRequest manifests in Git (GitOps source of truth)
- Crossplane managed resources recoverable from Kubernetes etcd backups
- Route53 records remain intact even if cluster fails
- infra-dns-api state in DynamoDB (existing backup/restore)
- Recovery: Restore cluster + DynamoDB, ArgoCD re-syncs all resources
