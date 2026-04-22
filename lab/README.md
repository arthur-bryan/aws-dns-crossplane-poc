# Local Lab — APE DNS Crossplane POC

Self-contained local environment for testing Crossplane compositions, XRDs, and
Backstage templates against **real AWS Route53** (no LocalStack).

## What this lab runs

| Component       | Where                       | Purpose                                                          |
|-----------------|-----------------------------|------------------------------------------------------------------|
| Kind cluster    | `ape-dns-lab`               | Single-node k8s, ports 80/443 mapped                             |
| ingress-nginx   | `ingress-nginx` ns          | Host-based routing for Argo/Backstage                            |
| Crossplane 2.x  | `crossplane-system` ns      | Composition engine                                               |
| Functions       | cluster-wide                | `function-go-templating`, `function-auto-ready`                  |
| AWS providers   | cluster-wide                | `provider-aws-route53`, `provider-aws-cloudformation` (v2.5.3+)  |
| ArgoCD          | `argocd` ns                 | Syncs this repo → cluster                                        |
| Backstage       | `lab/backstage/ape-lab/`    | Runs with `yarn dev`, opens PR against this repo                 |

## Layout

```
lab/
├── Makefile                         # make up / down / status / aws-creds
├── kind/cluster.yaml
├── bootstrap/
│   ├── 00-kind.sh
│   ├── 10-ingress.sh
│   ├── 20-crossplane.sh
│   └── 30-argocd.sh
├── crossplane/functions.yaml        # cluster Functions (go-templating, auto-ready)
├── argocd/
│   ├── root-app.yaml                # App-of-Apps
│   ├── values.yaml
│   └── apps/
│       ├── 01-crossplane-providers.yaml
│       ├── 02-crossplane-compositions-dns.yaml
│       ├── 03-lab-provider-config.yaml
│       └── 04-entities.yaml
├── provider-config/
│   └── dev-account.yaml             # lab ClusterProviderConfig (source: Secret)
├── samples/                         # direct-kubectl XR smoke tests
│   ├── 01-zone-example-com.yaml
│   ├── 02-record-a.yaml
│   ├── 03-record-alias-cloudfront.yaml
│   └── 04-record-weighted-bluegreen.yaml
├── backstage-templates/             # lab-adapted (vanilla-Backstage) templates
│   ├── catalog-info.yaml
│   ├── zone.yaml
│   ├── record.yaml
│   └── record-edit.yaml
└── backstage/
    ├── app-config.example.yaml      # committed template
    └── ape-lab/                     # scaffolded app (gitignored except config)

entities/
├── catalog-info.yaml                # Backstage Domain/System/Environment seed
└── environments/
    └── marketing/websites/corporate-site/dev/
        ├── namespace.yaml
        └── resources/aws/           # Zone/Record XRs land here from PRs
```

## Prerequisites

- Docker / docker-desktop / Rancher Desktop running
- `kind` v0.25+, `kubectl` v1.28+, `helm` v3.14+
- `node` 20 LTS + `yarn` 1.x (for Backstage)
- AWS credentials that can `route53:*`, provided via `~/.aws/credentials`
- GitHub PAT (classic, `repo` scope) for Backstage → PR and Argo → repo

## Quick start

```bash
# 1. Bring up cluster + platform
make -C lab up

# 2. Provide AWS creds
#    Put your Route53-capable credentials in ~/.aws/credentials (profile = default)
make -C lab aws-creds

# 3. Open Argo UI
make -C lab argo-port          # → http://localhost:8081
make -C lab argo-password      # prints initial admin password
# or: http://argocd.localtest.me directly

# 4. Point Argo at this repo (requires the push happened already)
kubectl apply -f lab/argocd/root-app.yaml

# 5. Sanity check via kubectl (no Backstage needed)
kubectl apply -f lab/samples/01-zone-example-com.yaml
kubectl get zone.dock.tech -A
kubectl get zones.route53.aws.m.upbound.io -A
```

## Tearing down

```bash
make -C lab down               # kind delete cluster
```

The three production chart directories (`crossplane-compositions-dns/`,
`crossplane-providers/`, `crossplane-provider-config-aws/`) and the production
`backstage-templates/` are **never modified** by the lab. All local divergence
lives in `lab/`.

---

## End-to-end smoke test

Walks through zone creation → record creation → record edit, exercising every
moving piece (Backstage scaffolder → PR → Argo sync → Crossplane → Route53).

### 0. Pre-requisites checklist

```bash
# Cluster + platform up?
make -C lab status

# AWS creds applied?
kubectl -n crossplane-system get secret aws-creds
# If missing: make -C lab aws-creds

# Provider config healthy?
kubectl get clusterproviderconfig dev-account -o yaml | grep -A5 conditions:

# Argo app-of-apps applied + healthy?
kubectl -n argocd get applications

# Backstage running?
cd lab/backstage/ape-lab && \
  GITHUB_TOKEN=ghp_xxx yarn dev
# → http://localhost:3000
```

### 1. Create a Zone via Backstage

1. Browse to `http://localhost:3000` → **Create...** → pick **AWS Route53 DNS Zone (Lab)**.
2. Fill the form:
   - Name: `test-zone-lab`
   - System: pick `corporate-site` from EntityPicker
   - Environment: `dev`
   - Zone Name: `lab.example.com` (replace with a real sub-domain you control)
   - AWS Account ID: your 12-digit account
   - AWS Account Name: `dev-account` (must match the ClusterProviderConfig)
3. Submit → scaffolder runs → PR opened against this repo.

**Verify:**
```bash
# The PR should contain:
entities/environments/marketing/websites/corporate-site/dev/resources/aws/zone-test-zone-lab.yaml
```

### 2. Merge the PR and watch Argo sync

```bash
# Merge PR in GitHub UI or:
gh pr merge <pr-number> --squash --delete-branch

# Watch Argo sync (~30-60s)
kubectl -n argocd get applications entities -w

# Zone XR should appear
kubectl get zone.dock.tech -A
# NAME           SYNCED  READY  COMPOSITION
# test-zone-lab  True    True   zone
```

### 3. Verify the Route53 zone exists

```bash
# From your local AWS CLI (using same creds as aws-creds secret):
aws route53 list-hosted-zones --query 'HostedZones[?Name==`lab.example.com.`]'

# And nameservers pushed to XR status:
kubectl get zone.dock.tech test-zone-lab \
  -n system-corporate-site-dev \
  -o jsonpath='{.status.nameServers}' | jq .
```

### 4. Create a record via Backstage

1. `http://localhost:3000` → **Create...** → **AWS Route53 DNS Record (Lab)**.
2. Fill the form:
   - Name: `www-lab`
   - System: `corporate-site`, Environment: `dev`
   - Parent Zone: `lab.example.com`
   - Record Name: `www.lab.example.com`
   - Type: `A` → Values: `[192.0.2.1]`, TTL: `300`
3. Submit → merge the PR.

**Verify:**
```bash
kubectl get record.dock.tech -A
# NAME     SYNCED  READY  COMPOSITION
# www-lab  True    True   record

# Two MRs created by the composition:
kubectl get records.route53.aws.m.upbound.io -A   # A record
kubectl get zones.route53.aws.m.upbound.io -A     # observe-only zone lookup

# DNS resolves after ~TTL seconds
dig +short www.lab.example.com @<one-of-your-nameservers>
```

### 5. Edit a record via record-edit template

1. Backstage → **Create...** → **Edit AWS Route53 DNS Record (Lab)** (under hidden/tag=lab).
2. Pre-fill:
   - Name: `www-lab`, System: `corporate-site`, Environment: `dev`
   - Type: `A` (immutable, disabled), Record Name: `www.lab.example.com` (immutable, disabled)
   - Values: `[192.0.2.5, 192.0.2.6]` (new), TTL: `60`
3. Submit → PR #2 opened → merge.

**Verify:**
```bash
kubectl get record.route53.aws.m.upbound.io www-lab -n system-corporate-site-dev \
  -o jsonpath='{.spec.forProvider.records}'
# ["192.0.2.5","192.0.2.6"]

# TTL reflected:
kubectl get record.route53.aws.m.upbound.io www-lab -n system-corporate-site-dev \
  -o jsonpath='{.spec.forProvider.ttl}'
# 60
```

### 6. Tear down the test resources (optional)

```bash
# Delete XRs — Crossplane cascades to Route53:
kubectl delete record.dock.tech www-lab -n system-corporate-site-dev
kubectl delete zone.dock.tech test-zone-lab -n system-corporate-site-dev

# Also delete the entity YAML + open cleanup PR:
#   git rm entities/environments/.../resources/aws/{zone,record}-*.yaml
#   git commit -m "chore(dns): tear down lab test" && gh pr create
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| XR stays `SYNCED=False` with `providerConfigRef.kind` error | provider at v1.x (legacy only) | Confirm `provider-aws-route53` at v2.5.3+ (`kubectl get providers.pkg.crossplane.io`) |
| MR stays `Creating` forever | no AWS creds | `make -C lab aws-creds`; check `kubectl -n crossplane-system get secret aws-creds` |
| MR reconcile: `AccessDenied` | IAM policy lacks Route53 perms | attach `AmazonRoute53FullAccess` (or least-priv equivalent) to the account used by `aws-creds` |
| Backstage Scaffolder: `Unable to find action: roadiehq:utils:fs:write` | `@roadiehq/scaffolder-backend-module-utils` not registered | verify `packages/backend/src/index.ts` has `backend.add(import('@roadiehq/scaffolder-backend-module-utils'))` |
| Scaffolder fails at `publish:github:pull-request` | PAT missing or expired | `export GITHUB_TOKEN=ghp_…` before `yarn dev` |
| Argo app `entities` stuck `OutOfSync` | branch not pushed / path wrong | `git push origin feature/ape-platform-alignment`; check `path: entities` in `lab/argocd/apps/04-entities.yaml` |
| Zone-lookup MR in Record never reaches `Ready` | the parent Zone doesn't exist in Route53 yet | create the Zone first (step 1 above) then retry the Record |
