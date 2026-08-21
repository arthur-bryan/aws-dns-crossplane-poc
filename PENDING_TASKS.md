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

## APE catalog→XR emulation (this session)

Context: the APE-aligned templates (`backstage-templates/templates/
resources/aws/*.yaml`, loaded by the lab via URL Locations) write
Backstage **catalog Resource** entities to
`entities/dock-tech/systems/<ns>/resources/<env>/{record,zone}-*.yaml`.
Crossplane does **not** reconcile those — it reconciles **XRs** under
`entities/environments/**` (the ArgoCD `entities` app's watch path).
In real APE a controller bridges the two; the lab had no such bridge, so
form submissions never reached Route53. This session built that bridge.

### TASK-17: ✅ Catalog→XR converter
`lab/tools/catalog_to_xr.py` — maps catalog Resource (`spec.type:
Record|Zone`) → Crossplane XR (`dock.tech/v1`). Key transforms:
`recordType→type`, `zone{id,name}→zoneId+zoneName`, FQDN `recordName`
relativized against `zoneName`, `aws.account` cast string→int (CRD
requires a number), routing/alias passthrough. Output path:
`entities/environments/<domain>/<subdomain>/<system>/<env>/resources/
aws/<zoneName>/...`. `--check` flag for CI drift detection.

### TASK-18: ✅ GitHub Action runs the converter (GitOps-pure)
`.github/workflows/catalog-to-xr.yml` — on push to
`feature/ape-platform-alignment` touching `entities/dock-tech/systems/
**/resources/**`, runs the converter and commits the generated XRs to
`entities/environments/` (only that path, so no self-trigger loop).
ArgoCD then applies. Validated end-to-end via API:
- **create**: `apitest.arthurbryan.com A 300 → 192.0.2.50` reached
  Route53, XR `Ready=Available`.
- **claim**: `claimtest.arthurbryan.com A 600 → 203.0.113.77` adopted
  via external-name; converter relativized the FQDN recordName.

### TASK-19: ✅ Templates emit the denormalized Resource contract
`record.yaml` (create) + `record-claim.yaml` (claim) now write a
self-contained Resource (system, environment, domain, subdomain, aws
account, zoneId, zoneName, recordName, recordType, ttl/values/…) so the
converter maps 1:1 with no cross-entity lookups. Create's zone field
switched from a catalog `EntityPicker` to the env-scoped
`AwsDnsZonePicker` (object); claim's `zoneId(string)` → `zone(object)`;
claim owner now derived from the System (dropped the unregistered
`MyGroupsPicker`). `infrastructure` System gained `aws.{account,
accountName}` per environment (dev/hml/prd) to feed `deriveAccount`.

### TASK-20: ✅ Picker fixes for the new frontend system
- `AwsDnsZonePicker` registered with `returnValue: z.object({id,name})`
  (it emits an object; mismatched `z.string` left the object-typed field
  unbound and the dropdown inert). Pickers imported directly, bypassing
  the barrel that double-registered them via the legacy
  `createScaffolderFieldExtension`.
- `dns` backend plugin → pluginId `aws`, routes `/dns-zones`,
  `/dns-records` (matches `discoveryApi.getBaseUrl('aws')`).
- `AwsDnsRecordPicker` excludes already-onboarded records (queries the
  catalog, builds an `<fqdn>|<type>` set from lab- AND APE-shape
  entities) so a claimed record can't be claimed again.
- catalog file-watcher now also ingests `entities/dock-tech/systems/**/
  resources/**` so onboarded records list under their System.

### TASK-21: ⏳ Edit template (standalone system→env→record)
**Not done.** Entry point: a record carries `spec.system`, so it lists
under its System in the catalog; the pencil opens `dns-record-edit`
pre-filled (zones aren't system-linked, so they don't appear). Remaining:
(a) fix the pre-existing hardcoded-`dev` write path in `record-edit.yaml`
(line ~257) — it has no `environment` field to derive the real env;
(b) make its `roadiehq:utils:merge` writeFile preserve the denormalized
fields while updating ttl/values/type; (c) verify records list under the
System and the pencil resolves. **NB:** the pencil-exclusion + standalone
listing depend on the catalog ingesting the dock-tech/systems Resources
(TASK-20, done).

### Test artifacts left in place
`apitest.arthurbryan.com` and `claimtest.arthurbryan.com` were created in
Route53 + git during API validation and are still live (XRs +
`entities/dock-tech/systems/.../record-{apitest,claimtest}-prd.yaml` +
generated XRs). Delete the catalog Resources (and let the converter prune,
or remove the XRs) when no longer needed.

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
