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

**Windows 10 vs Windows 11.** WSL2 `networkingMode=mirrored` (which would make LAN access zero-config) requires **Windows 11 22H2+**. On Windows 10 (this host, build 19045), WSL silently falls back to NAT mode, so we have to bridge the NAT with `netsh interface portproxy`. The script below handles that idempotently.

### What's auto-started vs. what needs a one-time manual step

| Layer | After WSL / PC reboot | How |
|---|---|---|
| kind cluster + everything inside it (Crossplane, Argo, catalog) | auto | Docker daemon + `restart=unless-stopped` |
| Backstage (UI + API) | auto | systemd user service `ape-backstage.service` + lingering |
| Windows firewall rules | auto | Persistent once created by the script |
| `netsh` portproxy rules | **manual — re-run script** | WSL2 NAT rotates the WSL IP each boot, so rules need re-pointing |

The third row is the only friction. A one-liner handles it.

### One-time lab-host setup

All of these have already been executed on this checkout; listed here so a fresh clone can replay them.

```bash
# kind container auto-starts when Docker daemon starts
make -C lab autostart-on

# Backstage auto-starts as a systemd user service (survives WSL restart)
make -C lab install-service
```

On the Windows side, `%USERPROFILE%\.wslconfig` intentionally contains no `networkingMode` line (mirrored mode doesn't work on Win10 — see the file's comments for how to enable it once you're on Win11).

### After every WSL restart: refresh portproxy

From an **elevated Windows PowerShell** on the lab host (right-click → Run as Administrator):

```powershell
cd \\wsl$\Ubuntu\home\bryan\github\aws-dns-crossplane-poc\lab\windows
Set-ExecutionPolicy -Scope Process Bypass
.\ape-lab-portproxy.ps1
```

The script:
1. Reads the current WSL2 IP (`wsl hostname -I`).
2. Rewrites 4 `netsh interface portproxy` rules (80, 443, 3000, 7007) to point at it.
3. Creates inbound firewall rules for those ports on first run (idempotent thereafter).
4. Prints the lab host's LAN IPv4 and the URLs the client PC should use.

This is the only step you need after `wsl --shutdown` or a PC reboot. It takes ~2 seconds.

If you want to skip even that: pin your WSL IP by adding `[network] generateHosts=false` / static routes, or upgrade to Windows 11 and uncomment the mirrored-mode block in `.wslconfig`.

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

Find the lab host's LAN IPv4 from `ape-lab-portproxy.ps1` output (or on the lab host: `ipconfig | findstr IPv4`).

| Service | URL |
|---|---|
| Backstage | `http://<WIN_LAN_IP>:3000` |
| Backstage API | `http://<WIN_LAN_IP>:7007` |
| ArgoCD | `http://<WIN_LAN_IP>/` — no hosts-file entry needed (a catch-all Ingress routes any hostname on :80 to `argocd-server`) |

No PowerShell, firewall, or hosts-file work on the client PC — it just makes outbound connections.

> If you ever need to run a second HTTP service behind port 80, drop `lab/argocd/ingress-ip-catchall.yaml` and re-introduce a hosts-file entry, otherwise the catch-all rule will hijack it.

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
