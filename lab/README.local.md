# Local Lab — Setup Guide

Everything needed to run the DNS lab on your personal PC and test the
`EnvironmentPicker`, `AwsDnsZonePicker`, and `AwsDnsRecordPicker` pickers end-to-end.

---

## Prerequisites

- Docker Desktop running
- `kind` installed
- `kubectl` installed
- `helm` installed
- `gh` CLI installed and authenticated (`gh auth login`)
- `nvm` installed, Node.js 22 active (`nvm install 22 && nvm use 22`)
- AWS CLI configured with credentials for an admin account that can assume roles in the DNS accounts
- 3 AWS DNS accounts (dev, hml, prd) with `backstage-role` created (see step 1)

---

## 1. IAM Role Setup (one-time, per DNS account)

Create a role named `backstage-role` in **each** of your 3 DNS accounts (dev, hml, prd).

**Trust policy** — allows the account where you run Backstage locally to assume it.
Replace `<ADMIN-ACCOUNT-ID>` with your personal/admin AWS account ID:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::<ADMIN-ACCOUNT-ID>:root" },
    "Action": "sts:AssumeRole"
  }]
}
```

**Permission policy** — read-only Route53:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "route53:ListHostedZones",
      "route53:ListHostedZonesByName",
      "route53:ListResourceRecordSets",
      "route53:GetHostedZone"
    ],
    "Resource": "*"
  }]
}
```

Save each as a JSON file, then run (once per DNS account, using the appropriate profile):
```bash
aws iam create-role \
  --role-name backstage-role \
  --assume-role-policy-document file://trust-policy.json \
  --profile <dns-account-profile>

aws iam put-role-policy \
  --role-name backstage-role \
  --policy-name route53-readonly \
  --policy-document file://permission-policy.json \
  --profile <dns-account-profile>
```

---

## 2. Environment Variables

Export these before starting Backstage. Add to `~/.bashrc` for persistence:

```bash
# DNS account IDs
export DNS_ACCOUNT_ID_DEV=<dev-dns-account-id>
export DNS_ACCOUNT_ID_HML=<hml-dns-account-id>
export DNS_ACCOUNT_ID_PRD=<prd-dns-account-id>

# Role ARNs (backstage-role created in step 1)
export DNS_ROLE_ARN_DEV=arn:aws:iam::${DNS_ACCOUNT_ID_DEV}:role/backstage-role
export DNS_ROLE_ARN_HML=arn:aws:iam::${DNS_ACCOUNT_ID_HML}:role/backstage-role
export DNS_ROLE_ARN_PRD=arn:aws:iam::${DNS_ACCOUNT_ID_PRD}:role/backstage-role

# GitHub token (or use: gh auth login — backstage-up.sh reads it automatically)
export GITHUB_TOKEN=<your-github-pat>
```

Verify `make dns-env` shows all 6 as set:
```bash
make -C lab dns-env
```

Verify assume-role works from your machine:
```bash
aws sts assume-role \
  --role-arn $DNS_ROLE_ARN_PRD \
  --role-session-name test
```
If this fails with `AccessDenied`, the trust policy in step 1 is wrong.

---

## 3. First-Time Cluster Setup

```bash
# From repo root — creates kind cluster, installs Crossplane + ArgoCD + App-of-Apps
make -C lab up

# Apply AWS credentials so Crossplane can manage Route53
make -C lab aws-creds
```

Wait for ArgoCD to sync all apps (~3-5 min). Check status:
```bash
make -C lab status
```

ArgoCD UI: http://argocd.localtest.me — password: `make -C lab argo-password`

---

## 4. Install Backstage Dependencies

Only needed after first clone or after `package.json` changes (new AWS SDK deps were added):

```bash
cd lab/backstage/ape-lab
yarn install
```

This installs:
- `@aws-sdk/client-route-53` — Route53 API client (backend)
- `@aws-sdk/credential-providers` — `fromTemporaryCredentials` for STS assume-role (backend)
- `express` + `@types/express` — DNS routes HTTP handler (backend)
- `@material-ui/lab` — `Autocomplete` component used by zone/record pickers (frontend)

---

## 5. Start Backstage

DNS env vars from step 2 must be set in the same shell:

```bash
# From repo root
make -C lab backstage-up

# Tail logs (bundle takes ~60-90s on cold start)
make -C lab backstage-log
```

Open http://localhost:3000

If `app-config.local.yaml` doesn't exist yet, `backstage-up.sh` creates it from
`lab/backstage/app-config.example.yaml` automatically. If it already existed from a
previous run, verify it contains the full `dns:` block:

```yaml
dns:
  accounts:
    dev:
      accountId: ${DNS_ACCOUNT_ID_DEV}
      roleArn: ${DNS_ROLE_ARN_DEV}
    hml:
      accountId: ${DNS_ACCOUNT_ID_HML}
      roleArn: ${DNS_ROLE_ARN_HML}
    prd:
      accountId: ${DNS_ACCOUNT_ID_PRD}
      roleArn: ${DNS_ROLE_ARN_PRD}
```

---

## 6. Verify DNS Backend Routes

Test the backend directly before touching the UI:

```bash
# Should return JSON list of hosted zones
curl "http://localhost:7007/api/dns/zones?environment=prd"

# Should return JSON list of records (use a real zone ID from the above response)
curl "http://localhost:7007/api/dns/records?environment=prd&zoneId=Z03010981ALJFZB4QLU8W"
```

Both should return `{ "zones": [...] }` / `{ "records": [...] }`. If you get `500`:
- Check env vars are exported in the shell that started Backstage
- Check `app-config.local.yaml` has the `dns:` block (step 5)
- Run `make -C lab backstage-log` to see the error
- Run `aws sts assume-role` test from step 2

---

## 7. Verify Pickers in the UI

### EnvironmentPicker
The `EnvironmentPicker` reads `spec.environments` from the selected System catalog entity.
The `infrastructure` System in `entities/catalog-info.yaml` is pre-seeded with `dev`, `hml`, `prd`.

Open any scaffolder template that uses `EnvironmentPicker` (e.g. Create → AWS Route53 DNS Zone).
After selecting a System, the Environment dropdown should show the 3 environments.

### AwsDnsZonePicker
Appears after `EnvironmentPicker` in templates that use it (e.g. the record claim template once wired).
Calls `GET /api/dns/zones?environment=<selected>` and populates a zone dropdown.

### AwsDnsRecordPicker
Appears after `AwsDnsZonePicker`. Calls `GET /api/dns/records?environment=X&zoneId=Y`.
Returns the full record object (`name`, `type`, `ttl`, `values`, `aliasTarget`).

All three pickers use the exact same component structure as APE's `AwsAccountPicker`:
`ScaffolderField` wrapper, `useAsync` from `react-use`, `discoveryApi` + `fetchApi`.

---

## 8. Day-to-Day Usage

```bash
# Pause (preserves state — stops kind container + Backstage)
make -C lab pause

# Resume after PC reboot
make -C lab resume

# Full teardown (destructive — need full 'make up' next time)
make -C lab down
```

Optional — kind auto-starts on Docker daemon start (i.e. after PC boot):
```bash
make -C lab autostart-on
```

---

## 9. Lab Architecture

```
Browser (localhost:3000)
  └── Backstage Frontend (React — new frontend system, @backstage/frontend-defaults)
        ├── EnvironmentPicker   →  reads catalog entity spec.environments (no backend call)
        ├── AwsDnsZonePicker    →  GET /api/dns/zones?environment=X
        └── AwsDnsRecordPicker  →  GET /api/dns/records?environment=X&zoneId=Y
              └── Backstage Backend (localhost:7007)
                    └── dns plugin (packages/backend/src/modules/dns-routes/)
                          └── STS AssumeRole → backstage-role in DNS account
                                └── Route53 ListHostedZones / ListResourceRecordSets

Scaffolder Template Submit
  └── Writes XR YAML to entities/ directory via GitHub PR
        └── ArgoCD syncs PR after merge
              └── Crossplane → Route53 (real DNS changes in AWS)
```

**APE emulation notes:**
- Components are identical to APE (`ScaffolderField`, `useAsync`, `discoveryApi`/`fetchApi` pattern)
- Registration uses `FormFieldBlueprint.make` instead of `scaffolderPlugin.provide()` — required
  because the lab runs the new Backstage frontend system; APE runs the old system. Business logic is identical.
- `EnvironmentPicker` reads `spec.environments` from the catalog System entity (same as APE) — no static list.

---

## 10. Pending Tasks Before Full End-to-End

See `PENDING_TASKS.md` at repo root for the full task list. Key remaining items:

- **TASK-6**: Wire `AwsDnsZonePicker` into `record-claim.yaml` template (replace `EntityPicker` for zone)
- **TASK-7**: Wire `AwsDnsRecordPicker` into `record-claim.yaml` to auto-fill record fields
- **TASK-8**: Add `hml-account.yaml` to `lab/provider-config/` if hml is a separate Crossplane provider
- **TASK-9**: Validate that `dock.tech/import-existing: "true"` triggers `[Observe, Update]` in composition
