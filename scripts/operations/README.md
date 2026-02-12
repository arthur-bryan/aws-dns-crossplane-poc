# DNS Operations Scripts

Essential scripts for managing DNS zones across Route53, GitOps, and Kubernetes.

## Scripts Overview

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `import-zone.sh` | Import Route53 zone to GitOps | Initial zone import, new zones |
| `sync-gitops.sh` | Apply GitOps changes to cluster | After Git commit, manual sync |
| `rollback-zone.sh` | Revert zone to previous version | Fix mistakes, undo changes |
| `validate-zone.sh` | Validate YAML before applying | Before Git commit, testing |
| `reconcile-zone.sh` | Force Crossplane reconciliation | Zone stuck, manual refresh |
| `compare-state.sh` | Compare Git vs cluster state | Detect drift, troubleshooting |

---

## Usage Examples

### Import New Zone

```bash
# Query Route53 for zone ID
aws route53 list-hosted-zones --query 'HostedZones[?Name==`newzone.hml.dock.tech.`]'

# Import zone
./scripts/operations/import-zone.sh Z1234567890ABC newzone.hml.dock.tech dev

# Review, commit, and sync
git add gitops/dev/newzone.hml.dock.tech.yaml
git commit -m "Import newzone.hml.dock.tech from Route53"
git push origin main
./scripts/operations/sync-gitops.sh
```

### Update Existing Zone

```bash
# Edit zone YAML
vim gitops/dev/infradev.hml.dock.tech.yaml

# Validate changes
./scripts/operations/validate-zone.sh gitops/dev/infradev.hml.dock.tech.yaml

# Commit and sync
git add gitops/dev/infradev.hml.dock.tech.yaml
git commit -m "Add new records to infradev zone"
git push origin main
./scripts/operations/sync-gitops.sh
```

### Rollback Changes

```bash
# Rollback to 1 commit ago
./scripts/operations/rollback-zone.sh gitops/dev/infradev.hml.dock.tech.yaml 1

# Review, commit, and sync
git add gitops/dev/infradev.hml.dock.tech.yaml
git commit -m "Rollback infradev zone changes"
git push origin main
./scripts/operations/sync-gitops.sh
```

### Force Reconciliation

```bash
# Single zone
./scripts/operations/reconcile-zone.sh infradev-hml-dock-tech

# All zones
./scripts/operations/reconcile-zone.sh all
```

### Detect Drift

```bash
# Compare Git vs cluster
./scripts/operations/compare-state.sh gitops/dev/infradev.hml.dock.tech.yaml

# Or use drift detection (Git vs Route53)
../sync-zone-records.sh infradev.hml.dock.tech dev
```

---

## Workflow Patterns

### Pattern 1: Import Existing Zone

```bash
1. import-zone.sh Z123... zone.com dev
2. git add + commit + push
3. sync-gitops.sh
4. compare-state.sh (verify)
```

### Pattern 2: Update Zone Records

```bash
1. Edit YAML file
2. validate-zone.sh (check)
3. git add + commit + push
4. sync-gitops.sh
5. reconcile-zone.sh (if needed)
```

### Pattern 3: Rollback Mistake

```bash
1. rollback-zone.sh zone.yaml 1
2. Review diff
3. git add + commit + push
4. sync-gitops.sh
```

### Pattern 4: Sync Route53 Drift

```bash
1. ../sync-zone-records.sh zone.com dev
2. Review drift report
3. git add + commit + push
4. sync-gitops.sh
```

---

## Prerequisites

**Required Tools:**
- `kubectl` - Kubernetes CLI
- `yq` - YAML processor
- `jq` - JSON processor
- `aws` - AWS CLI (for import-zone.sh)
- `git` - Version control

**Kubernetes Access:**
```bash
kubectl get pods -n crossplane-system
kubectl get applications -n argocd
```

**AWS Credentials:**
```bash
aws configure
# or
export AWS_PROFILE=dnszone-dev
```

---

## Troubleshooting

### Zone not syncing

```bash
# Check ArgoCD application status
kubectl get application dns-gitops -n argocd

# Force sync
./scripts/operations/sync-gitops.sh all --force

# Check Crossplane reconciliation
./scripts/operations/reconcile-zone.sh all
```

### Validation fails

```bash
# Check YAML syntax
yq eval '.' gitops/dev/zone.yaml

# Check Kubernetes validation
kubectl apply --dry-run=server -f gitops/dev/zone.yaml

# Check required fields
./scripts/operations/validate-zone.sh gitops/dev/zone.yaml
```

### Rollback not working

```bash
# Check Git history
git log --oneline --follow gitops/dev/zone.yaml

# Manual rollback
git show HEAD~1:gitops/dev/zone.yaml > gitops/dev/zone.yaml
```

---

## Safety Features

**All scripts include:**
- Input validation
- Error handling (`set -e`)
- Backup creation (where applicable)
- Confirmation before destructive actions
- Clear next-step instructions

**No scripts will:**
- Delete Route53 zones (observe mode only)
- Auto-commit to Git (manual review required)
- Force push (manual push required)
- Run without confirmation
