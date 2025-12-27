# AWS DNS Crossplane POC

## Overview

This POC demonstrates DNS management using Crossplane and Kubernetes Custom Resources. It defines XRDs (Custom Resource Definitions) and Compositions that allow DNS records to be managed declaratively through Kubernetes.

## Purpose

Provide a Kubernetes-native way to manage AWS Route53 DNS resources using:
- **Crossplane**: Infrastructure as Kubernetes resources
- **AWS Provider**: Direct Route53 integration
- **ArgoCD**: GitOps reconciliation

## Scope

This POC focuses **exclusively** on DNS provisioning via Crossplane. It does NOT include:
- Approval workflows (managed by infra-dns-api)
- Deployment orchestration (managed by infra-dns-api)
- Freeze period validation (managed by infra-dns-api)
- Python/Lambda code (belongs in infra-dns-api)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              IDP Apps (Platform Teams)                  │
│                                                          │
│  kubectl apply dnsrequest.yaml                          │
│         ↓                                               │
│  DNSRequest XRD (Custom Resource)                       │
│         ↓                                               │
│  Crossplane Composition                                 │
│         ↓                                               │
│  AWS Provider (Route53)                                 │
│         ↓                                               │
│  DNS Records Created                                    │
└─────────────────────────────────────────────────────────┘
```

## Directory Structure

```
aws-dns-crossplane-poc/
├── platform/                    # Kubernetes platform components
│   ├── crossplane/
│   │   ├── xrds/
│   │   │   └── dnsrequest/      # DNSRequest Custom Resource Definition
│   │   │       ├── definition.yaml
│   │   │       └── composition.yaml
│   │   ├── providers/           # Crossplane provider installations
│   │   │   ├── aws-route53.yaml
│   │   │   └── patch-and-transform.yaml
│   │   └── configs/             # ProviderConfigs (AWS credentials)
│   │       ├── aws-default.yaml
│   │       └── multi-account.yaml
│   ├── argocd/
│   │   ├── applications/        # ArgoCD Application definitions
│   │   └── bootstrap/           # Bootstrap configs
│   └── policies/
│       └── kyverno/             # Policy definitions
├── applications/                # IDP Portal Emulation
│   └── dns-dashboard/           # Flask app simulating platform team requests
│       ├── app.py               # Web UI for submitting DNSRequest XRDs
│       ├── dns_provisioner.py   # Kubernetes client for XRD interaction
│       ├── templates/           # HTML templates
│       └── k8s/                 # Kubernetes deployment manifests
├── examples/
│   └── dns-requests/            # Example DNSRequest manifests
│       ├── 01-simple-a-record.yaml
│       ├── 02-alias-cloudfront.yaml
│       ├── 03-weighted-routing.yaml
│       └── 04-certificate-validation.yaml
├── docs/
│   ├── ARCHITECTURE.md          # System architecture
│   └── IDP_INTEGRATION.md       # Integration guide for platform teams
└── README.md                    # This file
```

## DNSRequest XRD

The core of this POC is the `DNSRequest` Custom Resource Definition that allows declarative DNS management.

### Supported Record Types

- **A** - IPv4 addresses
- **CNAME** - Canonical name records
- **TXT** - Text records
- **ALIAS** - AWS Route53 ALIAS records
- **Weighted** - Weighted routing policies

### Supported Actions

- `create_record` - Create new DNS records
- `create_weighted_record` - Create weighted routing records
- `update_record` - Update existing DNS records
- `update_weighted_record` - Update weighted routing records
- `create_hosted_zone` - Create new Route53 hosted zones

## Quick Start

### 1. Install Crossplane

```bash
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm install crossplane crossplane-stable/crossplane --namespace crossplane-system --create-namespace
```

### 2. Install AWS Provider

```bash
kubectl apply -f platform/crossplane/providers/aws-provider.yaml
```

### 3. Configure AWS Credentials

```bash
kubectl create secret generic aws-creds \
  -n crossplane-system \
  --from-literal=credentials="$(cat ~/.aws/credentials)"
```

### 4. Install DNSRequest XRD

```bash
kubectl apply -f platform/crossplane/xrds/dnsrequest/definition.yaml
kubectl apply -f platform/crossplane/xrds/dnsrequest/composition.yaml
```

### 5. Create a DNS Record

```bash
kubectl apply -f examples/dns-requests/01-simple-a-record.yaml
```

### 6. Check Status

```bash
kubectl get dnsrequest example-app-api
kubectl describe dnsrequest example-app-api
```

## Example: Create A Record

```yaml
apiVersion: dns.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: example-app-api
  namespace: dns-infrastructure
spec:
  action: create_record
  env: dev
  hostedzone: dev.example.com
  businessUnit: banking
  records:
    - name: api
      type: A
      ttl: "300"
      value: "10.0.1.100"
```

## Example: ALIAS to CloudFront

```yaml
apiVersion: dns.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: example-app-cdn
  namespace: dns-infrastructure
spec:
  action: create_record
  env: prd
  hostedzone: example.com
  businessUnit: global
  records:
    - name: cdn
      type: ALIAS
      aliasTarget:
        dnsName: d111.cloudfront.net
        hostedZoneId: Z2FDTNDATAQYW2
        evaluateTargetHealth: false
```

## Example: Weighted Routing (Blue/Green)

```yaml
apiVersion: dns.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: example-app-weighted
  namespace: dns-infrastructure
spec:
  action: create_weighted_record
  env: prd
  hostedzone: example.com
  businessUnit: banking
  records:
    - name: api
      type: A
      ttl: "60"
      recordAValue: "10.0.1.100"
      recordAWeight: 90
      recordASetIdentifier: blue
      recordBValue: "10.0.1.101"
      recordBWeight: 10
      recordBSetIdentifier: green
```

## IDP Portal Emulation

The `applications/dns-dashboard` directory contains a Flask-based web application that simulates an Internal Developer Platform (IDP) portal. This tool allows you to:

- **Test DNSRequest XRD**: Submit DNS requests through a web UI
- **Emulate Platform Teams**: Simulate how platform teams would interact with the XRD
- **Validate Compositions**: Verify Crossplane compositions work correctly
- **Demonstrate Self-Service**: Show self-service DNS provisioning workflow

### Running the IDP Portal

```bash
cd applications/dns-dashboard

# Install dependencies
pip install -r requirements.txt

# Set Kubernetes context (cluster with Crossplane installed)
export KUBECONFIG=/path/to/kubeconfig

# Run the portal
python app.py
```

Access the portal at http://localhost:3000

**Note**: The IDP portal interacts directly with Kubernetes DNSRequest custom resources. It does NOT go through infra-dns-api approval workflows - this simulates platform teams with direct XRD access.

## Integration with infra-dns-api

For legacy apps using the Slack bot (dns-lambda-trigger):
- Requests go through infra-dns-api approval workflows
- infra-dns-api deployment_executor creates DNSRequest YAML
- ArgoCD detects and syncs the YAML
- Crossplane provisions DNS records

See `infra-dns-api/src/deployment_executor_yaml_frozen/` for the integration module (not yet implemented).

## Documentation

- **docs/ARCHITECTURE.md** - Detailed system architecture
- **docs/IDP_INTEGRATION.md** - Guide for platform teams using DNSRequest XRD
- **examples/** - Complete example manifests

## Limitations

- This POC does NOT handle approvals, freeze periods, or deployment windows
- Governance is assumed to be handled by the IDP platform or infra-dns-api
- No rollback mechanism implemented (future work)
- Multi-record operations require multiple DNSRequest resources

## Future Enhancements

- Rollback composition for reverting changes
- Multi-record support in single DNSRequest
- Advanced routing policies (latency, geolocation)
- Health check integration
- TTL optimization recommendations

## Related Projects

- **infra-dns-api** - REST API and approval workflows for legacy apps
- **dns-lambda-trigger** - Slack bot frontend for legacy apps

---

**Focus**: DNS management via Crossplane
**Not Included**: Approvals, orchestration, Python code (see infra-dns-api)
**Status**: POC - Ready for platform team evaluation
