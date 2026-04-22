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
├── backstage-templates/             # scaffolder-compatible templates (zone/record/record-edit)
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
    └── cross/cloud/infrastructure/dev/
        ├── namespace.yaml
        └── resources/aws/           # Zone/Record XRs land here from PRs
```

## Prerequisites

- Docker / docker-desktop / Rancher Desktop running
- `kind` v0.25+, `kubectl` v1.28+, `helm` v3.14+
- `node` 22 LTS + `yarn` 4.x (Backstage's `engines` requirement; `.nvmrc` provided at `lab/backstage/.nvmrc`)
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

# 5. Cluster sanity — check XRDs and Composition are installed
kubectl get xrd
kubectl get compositions
```

> `lab/samples/*.yaml` are **reference XR shapes only**. Do NOT `kubectl apply`
> them. All Zone/Record lifecycle flows through the Backstage scaffolder →
> PR → ArgoCD path.

## Pausing / resuming (preserves state across PC reboots)

```bash
# End of day — stops Backstage + pauses the kind container (state preserved on disk)
make -C lab pause

# Next day — brings kind back and relaunches Backstage (~8–90s total)
make -C lab resume

# Optional: kind auto-starts whenever Docker daemon starts (i.e. after PC boot)
make -C lab autostart-on        # default is off; enabling skips the `docker start` step
```

`resume` is idempotent — runs cleanly whether the container is stopped or
already running. After a PC reboot, a single `make -C lab resume` brings
everything back: kind cluster, ArgoCD state, Crossplane providers, XRs,
AWS creds Secret, Backstage. No helm re-installs, no image re-pulls.

Backstage runs detached (pid + log at `lab/backstage/backstage.{pid,log}`):

```bash
make -C lab backstage-up        # start (reads GITHUB_TOKEN or gh auth token)
make -C lab backstage-down      # stop
make -C lab backstage-log       # tail -f the log
```

## LAN access (reach Backstage + Argo from another PC on your network)

**Setup uses WSL2 mirrored networking + systemd auto-start + one-time Windows firewall rules.** After initial setup, the lab comes back cleanly after `wsl --shutdown`, PC reboot, etc. — no manual intervention required beyond opening a browser.

### One-time WSL-side setup (already done for this lab)

These steps have already been executed on this checkout:

1. `%USERPROFILE%\.wslconfig` written with `networkingMode=mirrored` (WSL2 shares Windows' network — no NAT, no portproxy, no IP rotation).
2. `docker update --restart unless-stopped ape-dns-lab-control-plane` — kind container auto-starts when Docker daemon starts.
3. `make -C lab install-service` — installs `~/.config/systemd/user/ape-backstage.service` + enables lingering, so Backstage auto-starts when systemd-user starts (on WSL boot).

To re-run any of these on a fresh clone:

```bash
# 1. mirrored mode (needs Windows-side edit; see .wslconfig in your Windows %USERPROFILE%)
# 2. kind autostart
make -C lab autostart-on
# 3. Backstage autostart
make -C lab install-service
```

### One-time Windows-side setup

After `.wslconfig` exists, restart WSL from an elevated Windows PowerShell:

```powershell
wsl --shutdown
```

Wait ~10 seconds, then open a new WSL terminal (starts WSL back up with mirrored networking).

Then, still in elevated Windows PowerShell, open the four ports in the firewall:

```powershell
New-NetFirewallRule -DisplayName "APE lab — HTTP"       -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80
New-NetFirewallRule -DisplayName "APE lab — HTTPS"      -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443
New-NetFirewallRule -DisplayName "APE lab — Backstage"  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000
New-NetFirewallRule -DisplayName "APE lab — Backstage API" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 7007
```

One-time. Does not need re-running after reboots.

### Backstage baseUrl (one-time per install)

Backstage's frontend bundle embeds `app.baseUrl` / `backend.baseUrl` as absolute URLs so the browser knows where to call the API. If those say `http://localhost:*`, a LAN client browser tries to hit *its own* localhost. Fix: point baseUrl at the lab host's LAN IP.

Edit `lab/backstage/ape-lab/app-config.local.yaml` (gitignored personal config), replace `localhost` with your Windows LAN IPv4:

```yaml
app:
  baseUrl: http://192.168.1.100:3000   # <-- your Windows LAN IP
  listen: { host: 0.0.0.0, port: 3000 }
backend:
  baseUrl: http://192.168.1.100:7007   # <-- your Windows LAN IP
  listen: { host: 0.0.0.0, port: 7007 }
```

Restart the Backstage service to pick up the change:

```bash
systemctl --user restart ape-backstage
```

The lab host can still reach the same URL (loopback via its own LAN IP works), so you don't need a separate dev-vs-LAN config.

### On the client PC (the other Windows)

Find the lab host's LAN IPv4 (on the lab host):

```powershell
ipconfig | findstr IPv4
```

On the client:

| Service | URL |
|---|---|
| Backstage | `http://<WIN_LAN_IP>:3000` — works immediately, no config needed |
| Backstage API | `http://<WIN_LAN_IP>:7007` |
| ArgoCD | `http://argocd.localtest.me/` — add `<WIN_LAN_IP>  argocd.localtest.me` to `C:\Windows\System32\drivers\etc\hosts` (edit via Notepad "Run as administrator") |

No PowerShell or firewall work needed on the client PC — the client just makes outbound connections.

### What survives a WSL restart

With the setup above:

| Component | Auto-restarts? | How |
|---|---|---|
| kind cluster | ✅ | Docker daemon starts with WSL; container has `restart=unless-stopped` |
| Crossplane + Argo + Backstage catalog | ✅ | All inside the kind cluster — come up with kind |
| Backstage (UI + API) | ✅ | systemd user service (`ape-backstage.service`); lingering enabled |
| Windows port exposure | ✅ | Mirrored mode eliminates WSL2 NAT; ports on Windows LAN IP match WSL2 ports |
| Windows firewall rules | ✅ | Persistent once created |

Nothing to re-run after WSL or PC restart. Just open the URL.

## Known limitations

- **`Edit AWS Route53 DNS Record` appears in `/create`.** It shouldn't — edits are meant to be reached via the pencil icon on a record's catalog entity page, which pre-fills the form with the record's identity. Hiding tag-filtered templates from `/create` requires a `PageBlueprint` override in Backstage's new frontend system (~1h of TypeScript plugin work + tests). The template's title is prefixed with ⚠️ and its description strongly nudges users toward the pencil-icon flow. Track in [todo].

## Tearing down (destructive)

```bash
make -C lab down               # kind delete cluster — wipes all cluster state
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

1. Browse to `http://localhost:3000` → **Create...** → pick **AWS Route53 DNS Zone Template**.
2. Fill the form:
   - System: pick `infrastructure` from EntityPicker
   - Environment: `dev`
   - Zone Name: a real sub-domain you control (e.g. `test.arthurbryan.com`)
   - AWS Account ID: your 12-digit account
   - AWS Account Name: `dev-account` (must match the ClusterProviderConfig)
3. Submit → scaffolder runs → PR opened against this repo.

**Verify:** the PR should contain one new file at
`entities/environments/cross/cloud/infrastructure/dev/resources/aws/zone-test.arthurbryan.com.yaml`,
and the XR inside has `metadata.name: zone-test.arthurbryan.com`.

### 2. Merge the PR and watch Argo sync

```bash
# Merge PR in GitHub UI or:
gh pr merge <pr-number> --squash --delete-branch

# Watch Argo sync (~30-60s)
kubectl -n argocd get applications entities -w

# Zone XR should appear
kubectl get zone.dock.tech -A
# NAME                       SYNCED  READY  COMPOSITION
# zone-test.arthurbryan.com  True    True   zone
```

### 3. Verify the Route53 zone exists

```bash
# From your local AWS CLI (using same creds as aws-creds secret):
aws route53 list-hosted-zones --query 'HostedZones[?Name==`test.arthurbryan.com.`]'

# And nameservers pushed to XR status:
kubectl get zone.dock.tech zone-test.arthurbryan.com \
  -n system-infrastructure-dev \
  -o jsonpath='{.status.nameServers}' | jq .
```

### 4. Create a record via Backstage

1. `http://localhost:3000` → **Create...** → **AWS Route53 DNS Record Template**.
2. Fill the form:
   - System: `infrastructure`, Environment: `dev`
   - Parent Zone: `test.arthurbryan.com`
   - Record Name: `api-test` (short form — will become `api-test.test.arthurbryan.com`)
   - Type: `A` → Values: `[192.0.2.1]`, TTL: `300`
3. Submit → merge the PR. File created at
   `entities/environments/cross/cloud/infrastructure/dev/resources/aws/record-api-test.test.arthurbryan.com.yaml`.

**Verify:**
```bash
kubectl get record.dock.tech -A
# NAME                                 SYNCED  READY  COMPOSITION
# record-api-test.test.arthurbryan.com  True    True   record

# Two MRs created by the composition:
kubectl get records.route53.aws.m.upbound.io -A   # A record
kubectl get zones.route53.aws.m.upbound.io -A     # observe-only zone lookup

# DNS resolves after ~TTL seconds
dig +short api-test.test.arthurbryan.com @<one-of-your-nameservers>
```

### 5. Edit a record via record-edit template

1. Backstage → **Create...** → **Edit AWS Route53 DNS Record** (filtered under tag `hidden`).
2. Fill the identity fields (immutable in the XR, but required by the form to locate the file):
   - System: `infrastructure`, Environment: `dev`
   - Parent Zone: `test.arthurbryan.com`
   - Record Name: `api-test`
   - Type: `A`
   - Values: `[192.0.2.5, 192.0.2.6]` (new), TTL: `60`
3. Submit → PR #2 opened → merge.

**Verify:**
```bash
kubectl get record.route53.aws.m.upbound.io record-api-test.test.arthurbryan.com \
  -n system-infrastructure-dev \
  -o jsonpath='{.spec.forProvider.records}'
# ["192.0.2.5","192.0.2.6"]

# TTL reflected:
kubectl get record.route53.aws.m.upbound.io record-api-test.test.arthurbryan.com \
  -n system-infrastructure-dev \
  -o jsonpath='{.spec.forProvider.ttl}'
# 60
```

### 6. Tear down the test resources (APE-compliant deletion)

Deletion is a git operation — never `kubectl delete` the XR directly.

```bash
git checkout -b chore/remove-dns-smoke-test
git rm entities/environments/cross/cloud/infrastructure/dev/resources/aws/record-api-test.test.arthurbryan.com.yaml
git rm entities/environments/cross/cloud/infrastructure/dev/resources/aws/zone-test.arthurbryan.com.yaml
git commit -m "chore(dns): remove DNS smoke test resources"
gh pr create -f
gh pr merge --squash --delete-branch
# Argo prunes -> Crossplane deletes -> Route53 deletes
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
