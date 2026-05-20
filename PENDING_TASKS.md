## Pending Tasks — DNS Lab Readiness

Status legend: ✅ done, 🟡 partial / lab-only, ⏳ pending operator action, 🗑 retired / model changed.

### TASK-1: ⏳ Create dedicated read-only `backstage-role` in each DNS account
**Status:** *not strictly required for the current lab* — the lab's
`dns-poc` IAM user (in account 597230762851) already reaches dev (309)
and hml (382) via `OrganizationAccountAccessRole`, and uses its base
creds directly for prd. For *production* you still want a least-privilege
read-only role; see the trust + permission policy in the previous
revision of this file.

### TASK-2: ✅ `dns:` block populated in `app-config.local.yaml`
The lab's `app-config.local.yaml` now carries the three accounts
hard-coded (no env vars needed for the lab). The `app-config.example.yaml`
in `lab/backstage/` still uses `${DNS_ACCOUNT_ID_*}` / `${DNS_ROLE_ARN_*}`
for portability.

### TASK-3: ✅ `yarn install` performed in `lab/backstage/ape-lab`
`@aws-sdk/client-route-53`, `@aws-sdk/credential-providers`, and the
other new packages are pinned in `package.json` + `yarn.lock`.

### TASK-4: ✅ AssumeRole into dev / hml verified
Validated end-to-end via the dns-routes backend:
```
GET /api/dns/zones?environment=dev  -> 200 (empty)
GET /api/dns/zones?environment=hml  -> 200 (empty, post-teardown)
GET /api/dns/zones?environment=prd  -> 200 (1 zone, 3 records)
```
`backstage-up.sh` sources `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` from the `crossplane-system/aws-creds`
Secret automatically, so AssumeRole has a source credential.

### TASK-5: ✅ Live picker E2E (browser-equivalent flow)
EnvironmentPicker → AwsDnsZonePicker → AwsDnsRecordPicker chain validated
in browser AND via API-emulated flow. Claim was driven end-to-end against
a real Route53 record in `hml.arthurbryan.com` (since pruned in TASK-12).
Form pickers correctly populate from live AWS state.

### TASK-6: ✅ `AwsDnsZonePicker` wired into the claim template
Both the upstream template (`backstage-templates/templates/resources/aws/record-claim.yaml`)
and the new lab template (`lab/backstage-templates/record-claim.yaml`)
use it.

### TASK-7: ✅ `AwsDnsRecordPicker` added to the claim template
Same templates as TASK-6. The picker returns the full record object so
the form no longer asks the user for `name` / `type` / `ttl` / `values` /
`aliasTarget` — those are pulled live from Route53.

### TASK-8: ✅ `hml` environment added
- `lab/provider-config/hml-account.yaml` (ClusterProviderConfig +
  EnvironmentConfig for sandbox account 382598791794)
- `lab/backstage-templates/zone.yaml` `deriveAccount` jsonata maps
  `hml → 382598791794`, default VPC `vpc-067a880ce560341f8`
- `lab/stuck-mr-recoverer/10-configmap.yaml` `PROVIDER_ROLE_CHAIN`
  knows about hml's `OrganizationAccountAccessRole`

### TASK-9: 🗑 `import.existing` flow — model retired
Originally validated the [Observe, Update]-only adoption path with a
5-invariant test (`lab/tests/e2e/record-import.py`). Replaced by the
unified-lifecycle model (TASK-13): every record runs with full
`[Observe, Create, Update, Delete]` policies, including claimed ones.
The composition still computes `external-name` from `zoneId + fqdn +
type` so adoption still works (Observe finds the record, Create is
skipped); but `kubectl delete` now cascades to Route53 by design.

### TASK-10: ✅ System entities have `spec.environments` populated
`infrastructure-dev`, `infrastructure-hml`, and `infrastructure-prd`
Resource entities (kind=environment) are present in
`entities/catalog-info.yaml`. The `EnvironmentPicker` reads them to
populate the env dropdown for each scaffolder run.

### TASK-11: ✅ Claims require manual review/merge; create+edit auto-merge
`.github/workflows/scaffolder-auto-merge.yml` excludes
`scaffolder/record-claim-*` from auto-merge so a human approves every
claim (transfer of ownership of an existing AWS record). Create and
edit PRs still auto-merge. Workflow file lives on
`feature/ape-platform-alignment` (also on `main` from PR #256 for
default-branch registration).

### TASK-12: ✅ Single lifecycle for all records (no UI delete)
- Dropped `spec.import.existing` from the data model entirely.
- All records now use full management policies. `kubectl delete` on
  the XR cascades to Route53 (admin-level operation).
- Delete link removed from every catalog template output and from
  the 50+ already-merged catalog entries (`entities/**`).
- Backfilled the 3 hml claims to the new shape, then pruned them
  along with the hml zone and 38 prd e2e test records (PR #264).

### TASK-13: ✅ Pencil-edit pre-fills the form with current state
`record-edit.yaml`: new `cleanParams` jsonata step strips the legacy
`import` key; `backstage.io/edit-url` now encodes the **full** merged
params (TTL, values, routing policy, etc.). Restored
`dock.tech/aws-account-id` + `dock.tech/aws-account-name` annotations
that were being dropped on every edit (the regression flagged in PR
#260).

### TASK-14: ✅ Catalog auto-updates without manual `git pull`
Hybrid setup: URL-based catalog Location for the seed
(`raw.githubusercontent.com/.../entities/catalog-info.yaml`) +
chokidar file-watcher for per-zone / per-record entities (the
`catalog-file-watcher` backend module). `backstage-up.sh` runs a 30s
`git pull` poller so the local clone tracks merged PRs. Lag from PR
merge to UI is 30–60s; no human action needed.

### TASK-15: ✅ Claim form shows only the requester's groups as owner
`record-claim.yaml` uses `MyGroupsPicker` (custom Backstage scaffolder
field) so the owner dropdown only contains groups the requester
belongs to. `spec.owner` on the resulting catalog Resource entity is
set to whichever group they pick. **NB:** ownership is informational
only — see "Open items" below.

### TASK-16: ✅ Template + entity copy cleaned up
Stripped all comments from `lab/backstage-templates/*.yaml` and
`entities/**/*.yaml`. Trimmed verbose form hints and PR descriptions
to match the simpler `zone.yaml` / `record.yaml` style. The
`infrastructure` Group + System descriptions now read "Infrastructure
Services" (DNS, SFTP, email, AD…) not "platform networking".

---

## Open items (not in original PENDING_TASKS but worth tracking)

- **ZoneAssociation upjet bug** — second non-inline VPC association
  on a private zone trips a known upjet "empty result" failure. AWS
  state ends up correct (manually verified); the MR's `Ready` condition
  stays `Creating` due to a deeper Crossplane runtime gap that the
  recoverer's annotation-patching can't break out of. Worth filing
  upstream alongside `crossplane-contrib/provider-upjet-aws#1806`.

- **Cross-account VPC association** — `private-cross-account-vpc`
  scenario in `zone-scenarios.py` not exercised. Would compound the
  multi-VPC ZA bug above; defer until upstream fix.

- **Owner enforcement on edits** — deliberately deferred. `spec.owner`
  is informational; no UI gate hides the pencil for non-owners and no
  CI check blocks merge if PR author isn't in the owner group. Real
  enforcement requires moving Backstage off guest auth to GitHub
  OAuth and wiring User + Group entities first. Documented decision,
  not a bug.

- **No UI delete button by design** — admins delete via
  `kubectl delete record.dock.tech <name>` (cascades to Route53).
  No platform support for self-service deletion; revisit if real
  demand arises.
