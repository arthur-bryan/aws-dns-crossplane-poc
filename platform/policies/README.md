# Platform Policies

Validation policies enforcing DNS best practices and preventing conflicts.

## Kyverno ClusterPolicies

### unique-dns-records.yaml

Prevents duplicate DNS records cluster-wide using API call context.

**Rules:**

1. **unique-dns-record-name**
   - Prevents duplicate recordName + recordType + zoneId combinations
   - Queries all DNSRecord resources cluster-wide
   - Provides detailed error with conflicting resource location

2. **prevent-cname-with-other-types**
   - Blocks CNAME creation when other record types exist with same name
   - DNS protocol requirement: CNAME must be exclusive

3. **prevent-other-types-with-cname**
   - Blocks non-CNAME creation when CNAME exists with same name
   - Inverse of rule 2 for complete coverage

**Deployment Mode:**

Initial deployment uses `validationFailureAction: Audit` to:
- Log violations without blocking
- Analyze existing conflicts
- Fix violations before enforcement

Change to `Enforce` after validation period.

## Installation

### Prerequisites

```bash
kubectl create -f https://github.com/kyverno/kyverno/releases/download/v1.12.0/install.yaml
```

Verify installation:
```bash
kubectl get pods -n kyverno
```

### Deploy Policies

```bash
kubectl apply -f platform/policies/kyverno/
```

### Monitor Violations (Audit Mode)

```bash
# View policy reports
kubectl get policyreport -A

# Describe specific violations
kubectl describe policyreport <name> -n <namespace>

# Check Kyverno logs
kubectl logs -n kyverno -l app.kubernetes.io/component=kyverno
```

### Enable Enforcement

After validating no conflicts exist:

```bash
kubectl patch clusterpolicy unique-dns-records --type=merge -p '{"spec":{"validationFailureAction":"Enforce"}}'
```

## Testing

### Valid Scenario: Unique Records

```bash
kubectl apply -f - <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSRecord
metadata:
  name: unique-a-record
spec:
  zoneId: Z1234567890ABC
  recordName: app.example.com
  recordType: A
  values:
    - 192.0.2.1
EOF
```

Expected: Creates successfully

### Invalid Scenario: Duplicate Record

```bash
# Create second record with same name+type+zone
kubectl apply -f - <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSRecord
metadata:
  name: duplicate-a-record
spec:
  zoneId: Z1234567890ABC
  recordName: app.example.com
  recordType: A
  values:
    - 192.0.2.2
EOF
```

Expected (Enforce mode):
```
Error from server: admission webhook "validate.kyverno.svc-fail" denied the request:
policy DNSRecord/default/duplicate-a-record for resource violation:
unique-dns-records:
  unique-dns-record-name: DNS record 'app.example.com' of type 'A' already
  exists in zone 'Z1234567890ABC'. Existing record found in namespace 'default',
  resource 'unique-a-record'.
```

### Invalid Scenario: CNAME Conflict

```bash
# Create A record
kubectl apply -f - <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSRecord
metadata:
  name: a-record-first
spec:
  zoneId: Z1234567890ABC
  recordName: conflict.example.com
  recordType: A
  values:
    - 192.0.2.1
EOF

# Try to create CNAME with same name
kubectl apply -f - <<EOF
apiVersion: dns.crossplane.poc/v1alpha1
kind: DNSRecord
metadata:
  name: cname-conflict
spec:
  zoneId: Z1234567890ABC
  recordName: conflict.example.com
  recordType: CNAME
  values:
    - target.example.com
EOF
```

Expected (Enforce mode): Second command blocked with DNS protocol restriction error

## Performance

**API Call Latency:**
- Query overhead: ~50-100ms per validation
- Acceptable for DNS management (infrequent operations)
- Background: false (synchronous validation required)

**Resource Usage:**
- Kyverno webhook: ~100MB RAM
- Policy engine: Minimal CPU (<0.1 core)

## Alternative: OPA/Gatekeeper

For teams preferring Rego logic or requiring data sync architecture:

See: `docs/research/dns-idp-validation-patterns.md` Example 3

**Trade-offs:**
- Kyverno: YAML-based, API call context (simpler)
- Gatekeeper: Rego-based, data sync inventory (more powerful)

## Troubleshooting

**Policy not triggering:**
```bash
kubectl describe clusterpolicy unique-dns-records
kubectl logs -n kyverno -l app.kubernetes.io/component=kyverno --tail=100
```

**Audit reports not appearing:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get clusterpolicy -o yaml | grep validationFailureAction
```

**Performance issues:**
- Increase Kyverno webhook replicas
- Add resource limits
- Consider Gatekeeper with data sync (cached queries)
