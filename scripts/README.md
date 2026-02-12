# DNS Management Scripts

Operational scripts for DNS zone management with Crossplane and GitOps.

## Directory Structure

```
scripts/
├── operations/              # Operational scripts (import, sync, rollback)
│   ├── import-zone.sh      # Import Route53 zone to GitOps YAML
│   ├── sync-gitops.sh      # Apply GitOps changes to cluster
│   ├── rollback-zone.sh    # Rollback zone to previous version
│   ├── validate-zone.sh    # Validate YAML before applying
│   ├── reconcile-zone.sh   # Force Crossplane reconciliation
│   ├── compare-state.sh    # Compare Git vs cluster state
│   └── README.md           # Operations documentation
│
└── sync-zone-records.sh    # Drift detection (Git vs Route53)
```

## Quick Reference

| Task | Script |
|------|--------|
| Import new zone from Route53 | `operations/import-zone.sh` |
| Apply GitOps changes to cluster | `operations/sync-gitops.sh` |
| Rollback zone changes | `operations/rollback-zone.sh` |
| Validate zone YAML | `operations/validate-zone.sh` |
| Force zone reconciliation | `operations/reconcile-zone.sh` |
| Compare Git vs cluster | `operations/compare-state.sh` |
| Detect Route53 drift | `sync-zone-records.sh` |

## Common Workflows

### Import Existing Zone

```bash
./operations/import-zone.sh Z1234567890ABC newzone.hml.dock.tech dev
git add gitops/dev/newzone.hml.dock.tech.yaml
git commit -m "Import newzone from Route53"
git push origin main
./operations/sync-gitops.sh
```

### Update Zone Records

```bash
vim gitops/dev/infradev.hml.dock.tech.yaml
./operations/validate-zone.sh gitops/dev/infradev.hml.dock.tech.yaml
git add gitops/dev/infradev.hml.dock.tech.yaml
git commit -m "Update infradev zone records"
git push origin main
./operations/sync-gitops.sh
```

### Sync Route53 Drift

```bash
./sync-zone-records.sh infradev.hml.dock.tech dev
git add gitops/dev/infradev.hml.dock.tech.yaml
git commit -m "Sync Route53 drift for infradev"
git push origin main
./operations/sync-gitops.sh
```

### Rollback Changes

```bash
./operations/rollback-zone.sh gitops/dev/infradev.hml.dock.tech.yaml 1
git add gitops/dev/infradev.hml.dock.tech.yaml
git commit -m "Rollback infradev zone"
git push origin main
./operations/sync-gitops.sh
```

## Documentation

See `operations/README.md` for detailed usage, troubleshooting, and workflow patterns.
