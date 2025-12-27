# DNS Dashboard - IDP Portal Emulation

## Overview

This Flask application emulates an Internal Developer Platform (IDP) portal interacting with the DNSRequest Custom Resource Definition (XRD). It demonstrates how platform teams would use Kubernetes-native infrastructure provisioning for DNS management.

## Purpose

- **Test DNSRequest XRD**: Submit DNS requests through a web UI
- **Emulate Platform Teams**: Simulate self-service DNS provisioning
- **Validate Crossplane Compositions**: Verify that compositions work correctly
- **Demonstrate Workflows**: Show end-to-end DNS request lifecycle

## FAQ

### Q1: Why in-cluster only? Why not standalone deployment?

**Decision**: Flask app runs ONLY in Kubernetes cluster (no standalone deployment)

**Reasons**:
- **Consistency**: ConfigMaps ensure all code is in cluster-native format
- **RBAC**: ServiceAccount provides proper Kubernetes API permissions
- **No Drift**: Single source of truth (no standalone vs. ConfigMap discrepancies)
- **XRD Access**: Direct access to DNSZone and DNSRecord custom resources

**Deployment**: All Python code, templates, and static assets embedded in ConfigMaps:
- `dns-platform-code` - Python files (app.py, dns_provisioner.py, provisioner.py, validator.py)
- `dns-platform-templates` - Jinja2 HTML templates
- `dns-platform-static` - CSS stylesheets

### Q2: Why are there both `dns_provisioner.py` AND `provisioner.py`?

**`dns_provisioner.py`** - DNS Management (CURRENT POC FOCUS):
- **Purpose**: Manages DNS via DNSZone and DNSRecord XRDs
- **XRD**: `dns.crossplane.poc/v1alpha1` (DNSZone, DNSRecord)
- **Operations**: Create zones, create records, list zones/records, delete zones/records
- **Focus**: Direct Crossplane interaction - demonstrates IDP portal managing DNS infrastructure

**`provisioner.py`** - Application Provisioning (LEGACY):
- **Purpose**: Manages example application deployments (ClickCounterApp)
- **XRD**: `dns.platform.example/v1alpha1/ClickCounterApp`
- **Operations**: Deploy apps, list apps, delete apps
- **Focus**: Original POC demonstrated full stack (App + DNS). Kept for backward compatibility with existing templates.

### Q3: What are ConfigMap and Deployment used for?

**ConfigMaps** (`k8s/configmap.yaml`, `k8s/configmap-templates.yaml`, `k8s/configmap-static.yaml`):
- **Purpose**: Store application source code as Kubernetes data
- **Why?**: Run Flask app in-cluster WITHOUT building Docker image
- **How?**: Python files stored as YAML string values, mounted as volume in pod
- **Benefit**: Fast iteration - just `kubectl apply` to update code

**Deployment** (`k8s/deployment.yaml`):
- **Purpose**: Run Flask app inside Kubernetes cluster
- **Components**:
  - **Namespace**: Isolated `dns-platform` namespace
  - **RBAC**: ServiceAccount + ClusterRole + ClusterRoleBinding (permission to create/delete XRDs)
  - **Deployment**: Pod spec with volume mounts from ConfigMaps
  - **Service**: NodePort (port 30080) for external access
- **Why?**: When IDP portal needs to run AS PART of the cluster (not just local dev)

**Why ConfigMaps (not Docker image)**:
- **Fast iteration**: Just `kubectl apply -f k8s/` to update code
- **POC Focus**: Demonstrating XRD interaction, not production deployment patterns
- **No Registry**: No need for Docker image builds or registry
- **Production Alternative**: Build proper Docker image with frozen dependencies and versioning

## Architecture

### Runtime Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        IDP Portal (Flask App)                    │
│                                                                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │   app.py    │──│dns_provisioner.py│  │  provisioner.py  │  │
│  │  (Routes)   │  │ (DNSZone/Record) │  │ (ClickCounter)   │  │
│  └─────────────┘  └──────────────────┘  └──────────────────┘  │
│         │                  │                       │            │
│         └──────────────────┴───────────────────────┘            │
│                            │                                    │
│                   Kubernetes API Client                         │
└────────────────────────────┼────────────────────────────────────┘
                             ↓
                    Kubernetes API Server
                             ↓
                ┌────────────┴────────────┐
                ↓                         ↓
       DNSZone/DNSRecord XRDs      ClickCounterApp XRD
    (dns.crossplane.poc/v1alpha1)  (dns.platform.example)
                ↓                         ↓
         Crossplane                  Legacy Composition
         Composition
                ↓
         AWS Provider
                ↓
         Route53 DNS
```

### Deployment Architecture

**In-Cluster Only** (ConfigMap-based):
```
Kubernetes Cluster
  ├── ConfigMap: dns-platform-code
  │     ├── app.py (Flask routes, CURRENT)
  │     ├── dns_provisioner.py (DNSZone/DNSRecord XRD client)
  │     ├── provisioner.py (legacy ClickCounterApp)
  │     └── validator.py (input validation)
  │
  ├── ConfigMap: dns-platform-templates
  │     ├── base.html (layout)
  │     ├── index.html (main page)
  │     ├── dns_dashboard.html (zone management)
  │     ├── zone_detail.html (record management)
  │     └── resources.html (resource list)
  │
  ├── ConfigMap: dns-platform-static
  │     └── styles.css (application styling)
  │
  └── Deployment: dns-platform
        ├── Namespace: dns-platform
        ├── ServiceAccount: dns-platform (RBAC identity)
        ├── ClusterRole: dns-platform-manager (XRD permissions)
        ├── ClusterRoleBinding: dns-platform-manager-binding
        │
        └── Pod Spec:
              ├── Image: python:3.11-slim
              ├── Command: pip install flask kubernetes gunicorn && gunicorn app:app
              ├── Volume Mount: /app ← ConfigMap (code)
              ├── Volume Mount: /app/templates ← ConfigMap (HTML)
              └── Volume Mount: /app/static ← ConfigMap (CSS)
                    ↓
              Service: NodePort 30080
                    ↓
              External Access (port-forward or NodePort)
```

**Key Point**: This portal does NOT go through infra-dns-api approval workflows. It submits DNSRequest resources directly to Kubernetes, simulating platform teams with direct XRD access.

## Prerequisites

- Kubernetes cluster with Crossplane installed
- DNSZone and DNSRecord XRDs installed (`platform/crossplane/xrds/dnszone/`, `platform/crossplane/xrds/dnsrecord/`)
- AWS Provider for Crossplane configured
- kubectl configured with cluster access

## Deployment

All files embedded in ConfigMaps - no standalone deployment option.

```bash
cd applications/dns-dashboard/k8s

# Deploy all ConfigMaps and deployment
kubectl apply -f configmap.yaml           # Python code
kubectl apply -f configmap-templates.yaml # HTML templates
kubectl apply -f configmap-static.yaml    # CSS files
kubectl apply -f deployment.yaml          # App deployment with RBAC

# Verify deployment
kubectl get pods -n dns-platform
kubectl logs -n dns-platform deployment/dns-platform -f
```

## Access

**Option 1: Port Forward** (recommended for local testing)
```bash
kubectl port-forward -n dns-platform deployment/dns-platform 3000:3000
# Access at http://localhost:3000
```

**Option 2: NodePort** (if cluster nodes accessible)
```bash
# Access at http://<node-ip>:30080
```

## Features

### 1. List DNS Zones
Shows all deployed DNSRequest resources with action=create_hosted_zone

### 2. Create DNS Records
Submit a new DNSRequest XRD with:
- Record name (subdomain)
- Target zone (from deployed zones)
- Environment (dev, hml, prd)
- Record type (currently A records with 127.0.0.1)

### 3. View All Requests
List all DNSRequest resources with their:
- Name
- Hosted zone
- Environment
- Action
- Status
- Requester
- Creation timestamp

### 4. Delete Requests
Remove DNSRequest resources from Kubernetes

## DNSRequest XRD Interaction

The portal creates DNSRequest manifests like this:

```yaml
apiVersion: dns.infra.dock.tech/v1alpha1
kind: DNSRequest
metadata:
  name: record-myapp-example-com-a
  namespace: dns-infrastructure
spec:
  requesterName: "IDP Portal"
  action: create_record
  env: dev
  hostedzone: example.com
  businessUnit: shared
  originTicket: https://idp-portal.example.com/request/abc123
  records:
    - name: myapp
      type: A
      ttl: "300"
      value: "127.0.0.1"
```

## Files

### ConfigMaps (k8s/)

- **`configmap.yaml`** - Python code
  - **app.py**: Flask application (routes, handlers, HTTP endpoints)
  - **dns_provisioner.py**: Kubernetes client for DNSZone/DNSRecord XRDs
    - XRD: `dns.crossplane.poc/v1alpha1`
    - Methods: `create_zone()`, `create_record()`, `list_zones()`, `list_records()`, etc.
  - **provisioner.py**: Legacy ClickCounterApp XRD client
    - XRD: `dns.platform.example/v1alpha1/ClickCounterApp`
    - Kept for backward compatibility
  - **validator.py**: Input validation functions
    - `validate_project_name()`: 3-63 chars, lowercase alphanumeric + hyphens
    - `validate_domain()`: Standard DNS domain validation

- **`configmap-templates.yaml`** - Jinja2 HTML templates
  - **base.html**: Base layout with navigation
  - **index.html**: Main page (create app form)
  - **dns_dashboard.html**: DNS zone management with create zone modal
  - **zone_detail.html**: Individual zone details with record management
  - **resources.html**: List all provisioned resources

- **`configmap-static.yaml`** - CSS stylesheets
  - **styles.css**: Application styling (minimalist design)

- **`deployment.yaml`** - Kubernetes deployment manifest
  - Namespace, ServiceAccount, RBAC (ClusterRole, ClusterRoleBinding)
  - Deployment with volume mounts from all three ConfigMaps
  - Service (NodePort 30080)

### Jinja2 Templating

All HTML templates use **Jinja2 templating engine** (Flask default):

**Features Used**:
- Template inheritance: `{% extends "base.html" %}`
- Variable rendering: `{{ zone.name }}`
- Control flow: `{% for zone in zones %}`, `{% if not zones %}`
- URL generation: `{{ url_for('provision') }}`

**Template Structure**:
- **base.html**: Common layout (header, nav, footer)
- **Child templates**: Extend base, define content blocks

### Kubernetes Deployment

**Components**:

  1. **Namespace** (`dns-platform`)
     - Isolated namespace for IDP portal deployment

  2. **ServiceAccount** (`dns-platform`)
     - Identity for the Flask app pod
     - Used by RBAC for permission checks

  3. **ClusterRole** (`dns-platform-manager`)
     - **Permissions**:
       - `dns.crossplane.poc`: dnszones, dnsrecords (old XRDs)
       - `dns.platform.example`: clickcounterapps (legacy app XRD)
       - Core resources: secrets, configmaps (read-only)
     - **Why?**: Flask app needs to CREATE/UPDATE/DELETE custom resources via Kubernetes API

  4. **ClusterRoleBinding** (`dns-platform-manager-binding`)
     - Links ServiceAccount → ClusterRole
     - Grants permissions cluster-wide (not namespace-scoped)

  5. **Deployment** (`dns-platform`)
     - **Image**: `python:3.11-slim` (base Python image, NOT custom-built)
     - **Command**:
       ```bash
       pip install -q flask kubernetes python-dotenv gunicorn
       cd /app && gunicorn -w 2 -b 0.0.0.0:3000 app:app
       ```
     - **Why This Approach?**: No Docker build needed - dependencies installed at pod startup
     - **Volume Mounts**:
       - `/app` ← ConfigMap `dns-platform-code` (Python files)
       - `/app/templates` ← ConfigMap `dns-platform-templates` (Jinja2 HTML)
       - `/app/static` ← ConfigMap `dns-platform-static` (CSS files)
     - **ServiceAccount**: `dns-platform` (for Kubernetes API access)
     - **Probes**:
       - Liveness: `GET /health` every 10s (restart if fails)
       - Readiness: `GET /health` every 5s (remove from service if fails)

  6. **Service** (`dns-platform`)
     - **Type**: NodePort (accessible outside cluster)
     - **Port**: 80 → 3000 (external:internal)
     - **NodePort**: 30080 (fixed port on every cluster node)
     - **Access**: `http://<node-ip>:30080`

  **Why ConfigMap Instead of Docker Image?**
  - **Pros**: Fast iteration (just `kubectl apply`), no Docker registry needed, easy code updates
  - **Cons**: Slower startup (pip install on every pod start), not production-ready, no version control

## Updating the Application

To update code, templates, or styles:

```bash
# Edit the ConfigMap YAML files
cd applications/dns-dashboard/k8s

# Update Python code in configmap.yaml (data.app.py, data.dns_provisioner.py)
# Update HTML in configmap-templates.yaml (data.base.html, etc.)
# Update CSS in configmap-static.yaml (data.styles.css)

# Apply changes
kubectl apply -f configmap.yaml
kubectl apply -f configmap-templates.yaml
kubectl apply -f configmap-static.yaml

# Restart pod to pick up changes
kubectl rollout restart deployment/dns-platform -n dns-platform

# Verify
kubectl get pods -n dns-platform -w
```

## Production Deployment Alternative

For production, build a proper Docker image instead of using ConfigMaps:

```bash
# 1. Create Dockerfile with application code
# 2. Build image: docker build -t dns-dashboard:v1.0.0 .
# 3. Push to registry: docker push <registry>/dns-dashboard:v1.0.0
# 4. Update deployment.yaml to use image instead of ConfigMap volumes
# 5. Deploy: kubectl apply -f deployment.yaml
```

**Why Docker for Production**:
- Versioning and rollback capability
- Faster pod startup (no pip install at runtime)
- Immutable artifacts
- Better security scanning

## Limitations

- Currently only supports A record creation with hardcoded value (127.0.0.1)
- No support for ALIAS, weighted, or update operations (UI only)
- No integration with infra-dns-api approval workflows
- Minimal error handling and validation

## Future Enhancements

- Support all DNSRequest actions (ALIAS, weighted, update)
- Add form fields for custom record values
- Show DNSRequest status transitions in real-time
- Integrate with Crossplane resource status (Ready condition)
- Add YAML preview before submission
- Support namespace selection

## Related Documentation

- [DNSRequest XRD Definition](../../platform/crossplane/xrds/dnsrequest/definition.yaml)
- [Architecture Guide](../../docs/ARCHITECTURE.md)
- [IDP Integration Guide](../../docs/IDP_INTEGRATION.md)
- [Example DNSRequests](../../examples/dns-requests/)

---

**Status**: Functional prototype for testing DNSRequest XRD
**Use Case**: Platform team emulation, XRD validation, POC demonstration
