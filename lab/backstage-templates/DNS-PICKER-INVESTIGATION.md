# DNS Picker Investigation — Situation Report

## Goal

Validate why `AwsDnsZonePicker` and `AwsDnsRecordPicker` render as disabled plain-text
fields instead of interactive Autocomplete dropdowns in the APE Backstage platform.
Reproduce and fix the problem locally in the POC lab before pushing to APE repos.

## What is deployed in APE

### ape-platform-backstage-templates (develop branch)

All four DNS templates have been updated and merged (PRs #23, #26, #27):

- `record-claim.yaml` — "Claim Existing DNS Record"
  - `zone` field: `type: object`, `ui:field: AwsDnsZonePicker`
  - `existingRecord` field: `type: object`, `ui:field: AwsDnsRecordPicker`
  - `name` (context) field **removed** — entity name is derived automatically by
    `computeRecordName` JSONata step from the record picker result
  - `EnvironmentPicker` (not `AwsEnvironmentPicker`) — scopes environments to the
    selected system's `spec.environments`
- `record.yaml` — "DNS Record Template"
- `zone.yaml` — "DNS Zone Template"
- `record-edit.yaml` — "Edit DNS Record"
- All titles/descriptions cleaned of AWS/Route53 branding

### ape-platform-backstage (main branch, PR #18 merged 2026-06-03)

`AwsDnsZonePicker` — outputs `{ id: string, name: string }` object:
```ts
// schema.ts
output: (z) => z.object({ id: z.string(), name: z.string() })
```

`AwsDnsRecordPicker` — outputs full record object with `name`, `type`, `ttl`, `values`,
`aliasTarget?`, `setIdentifier?`, `weight?`.

Both registered via `scaffolderPlugin.provide(createScaffolderFieldExtension(...))` and
listed in `packages/app/src/extensions/scaffolder.tsx` under `<ScaffolderFieldExtensions>`.

Backend `/api/aws/dns-zones` and `/api/aws/dns-records` routes exist in
`plugins/aws-backend/src/router.ts`. They assume `backstage-role` in the target DNS
account via `fromTemporaryCredentials`.

IAM in `ape-platform-aws-setup` (`modules/crossplane-iam/iam.tf`):
- `backstage-role` trust policy trusts `ape-idp-dev-backstage` and `260029269338:role/backstage`
- `backstage-read-policy` includes `route53:ListHostedZones` and `route53:ListResourceRecordSets`
- Only `dnszone-hml` account has been onboarded (no `dnszone-dev` or `dnszone-prd` terraform)

## Root Cause Hypothesis

The zone/record pickers have been visually "disabled" (plain text, no dropdown) for over
48 hours after PR #18 merged. Two possible causes:

### Hypothesis 1 — Schema type mismatch blocked rendering (most likely)

Timeline of the mismatch:
- **2026-05-20**: `AwsDnsZonePicker` first added to `backstage/main` with `output: z.string()`
  (returned zone ID as a plain string). Templates at that time also used `type: string`.
- **2026-06-02**: Templates updated on `develop` to use `type: object` for the `zone` field
  (anticipating the object-output picker), but the deployed backstage JS bundle still had
  the **string-output** picker.
- **2026-06-03 13:35**: PR #18 merged to `backstage/main` — zone picker now outputs
  `z.object()`. Build triggered.

Between June 2 and the point where the new build deploys, the template declares
`type: object` but the registered extension returns a string. Backstage's scaffolder
may treat this type mismatch as an unresolvable field and fall back to RJSF's default
renderer for `type: object` (which renders a disabled non-interactive widget).

**If this is the cause:** the fix is simply waiting for the build + ArgoCD to deploy
the new image. To verify: check GitHub Actions on `ape-platform-backstage` for the
build triggered after `059bc19` (2026-06-03 13:35 BRT), then check ArgoCD sync status.

### Hypothesis 2 — Build never deployed correctly

The CI build may have failed or ArgoCD may not have synced. The deployed image could be
running an older commit that predates the DNS pickers entirely, while the templates
(deployed from a different repo via catalog, no build step) reference extensions that
don't exist in the JS bundle.

**Verification:** hit `<backstage-url>/api/aws/dns-zones?environment=hml` directly.
If 404 → backend route not deployed. If 401/403 → deployed but auth issue. If 500 →
deployed but IAM/STS issue.

### Hypothesis 3 — IAM / STS credential chain failing silently

The backend assumes `backstage-role` with `ExternalId: accountId`. The trust policy does
NOT require ExternalId — passing it when not required is harmless per AWS docs, so this
should not cause access denied.

The IRSA identity (`backstage-techdocs-publisher`) is NOT in the trust policy of
`backstage-role`. The trust policy trusts `ape-idp-dev-backstage`. Backstage runs as
the pod's IRSA identity first, then assumes `backstage-role`. If `ape-idp-dev-backstage`
is the role that Backstage's pod actually runs as (via IRSA annotation on its service
account), the chain works. If Backstage runs as a different identity
(`backstage-techdocs-publisher`), the AssumeRole call will fail with AccessDenied —
but this would surface as an HTTP 500 from the backend, not a disabled form field.

**Only affects `dnszone-hml`** — no `backstage-role` exists in `dnszone-dev` or
`dnszone-prd`.

## What the disabled field looks like

User reports: after selecting system and environment, the zone field shows its title
("DNS Zone") as static text with description "The hosted zone containing this record"
below it. The record field similarly shows "Existing Record". No API call to
`/api/aws/dns-zones` is made in the browser network panel.

This is the RJSF fallback for `type: object` when the registered custom field extension
is not found or not applicable — it renders a non-interactive generic object widget.

## Lab replication goal

This POC lab replicates both the templates and the picker components to allow local
testing without APE infrastructure. The lab uses:
- Same `AwsDnsZonePicker` and `AwsDnsRecordPicker` components (synced from APE main)
- Same template YAML (parameters section identical to APE develop)
- Lab-local backend DNS routes (no cross-account STS — configurable via `dns.accounts.<env>.roleArn`)
- Lab-local `EnvironmentPicker` that reads from catalog system `spec.environments`

### Files synced from APE in this commit

| Lab file | APE source |
|----------|-----------|
| `lab/backstage-templates/record-claim.yaml` | `ape-platform-backstage-templates/templates/resources/aws/record-claim.yaml` @ develop `3ebe12b` |
| `lab/backstage-templates/record.yaml` | same @ develop |
| `lab/backstage-templates/zone.yaml` | same @ develop |
| `lab/backstage-templates/record-edit.yaml` | same @ develop |
| `lab/backstage/ape-lab/…/AwsDnsZonePicker/AwsDnsZonePicker.tsx` | `ape-platform-backstage` @ main `059bc19` |
| `lab/backstage/ape-lab/…/AwsDnsZonePicker/schema.ts` | same (updated to `z.object`) |
| `lab/backstage/ape-lab/…/AwsDnsRecordPicker/AwsDnsRecordPicker.tsx` | APE main + lab-specific catalog filtering (excludes already-onboarded records) |

### Known lab vs APE differences

- **Registration API**: Lab uses new frontend system (`FormFieldBlueprint` / `createFormField`);
  APE uses old API (`scaffolderPlugin.provide` / `createScaffolderFieldExtension`).
  The registered `name:` strings are identical (`AwsDnsZonePicker`, `AwsDnsRecordPicker`),
  so the template `ui:field` references resolve the same way in both.
- **Backend auth**: Lab router accepts optional `roleArn` per account (no roleArn = use
  default credential chain, useful for local dev). APE always assumes `backstage-role`.
- **Record picker filtering**: Lab additionally filters out already-onboarded catalog
  records so they don't appear as claimable options. APE does not have this filtering.
- **Template steps**: Lab templates reference `$yaml: ../../../shared/entities/...`
  includes (copied from APE). These will fail if the form is actually submitted in the
  lab, since the shared entity YAMLs don't exist locally. The form/picker rendering
  itself is unaffected — submit-time failures are acceptable for picker testing.

## How to test locally

```bash
# 1. Start the lab
cd lab
make up          # or: make backstage-up

# 2. Open http://localhost:3000/create
# 3. Find "Claim Existing DNS Record" template
# 4. Select a System that has spec.environments configured
# 5. Environment picker should auto-select from system's environments
# 6. DNS Zone picker should show an Autocomplete (even if disabled pending env)
#    After env is selected → should load zones from /api/aws/dns-zones?environment=<env>
# 7. Check browser Network tab for the /api/aws/dns-zones call
```

Configure `app-config.yaml` DNS accounts for local testing:
```yaml
dns:
  accounts:
    hml:
      accountId: "729620324125"
      roleArn: "arn:aws:iam::729620324125:role/backstage-role"  # optional: omit if running with direct creds
```

## Next steps

1. Run the lab and confirm whether the pickers render as Autocomplete dropdowns
2. If pickers still show as disabled text in the lab → the bug is in the component/
   registration code itself, not a deployment lag
3. If pickers work in the lab → the APE issue is deployment lag (wait for ArgoCD sync)
   or an IAM issue (test `/api/aws/dns-zones` directly in the browser)
4. If the API call reaches the backend but returns an error → investigate IAM/STS chain
