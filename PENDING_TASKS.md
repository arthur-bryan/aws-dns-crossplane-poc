## Pending Tasks — DNS Lab Readiness

Status legend: ✅ done, 🟡 partial / lab-only, ⏳ pending operator action.

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
GET /api/dns/zones?environment=hml  -> 200 (empty)
GET /api/dns/zones?environment=prd  -> 200 (1 zone, 42 records)
```
`backstage-up.sh` sources `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` from the `crossplane-system/aws-creds`
Secret automatically, so AssumeRole has a source credential.

### TASK-5: 🟡 Live picker E2E — backend tested, frontend UX still manual
Backend half ✅ (see TASK-4). Frontend (EnvironmentPicker →
AwsDnsZonePicker → AwsDnsRecordPicker) lives at
`lab/backstage/ape-lab/packages/app/src/modules/scaffolder/` and is
registered in the scaffolder index. Manual smoke at
`http://localhost:3000/create/templates/default/aws-dns-record-claim`
recommended once you create a record in AWS that you want to claim.

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

### TASK-9: ✅ `import.existing` flow validated
Five-invariant regression test at `lab/tests/e2e/record-import.py`:
1. XR Synced+Ready in <60s, no Create attempt
2. MR `managementPolicies == [Observe, Update]`
3. AWS record byte-for-byte preserved on import
4. XR mutation propagates via Update path
5. Deleting the XR does NOT delete the AWS record (ownership preserved)

All five PASS against the live platform.

### TASK-10: ✅ System entities have `spec.environments` populated
`infrastructure-dev`, `infrastructure-hml`, and `infrastructure-prd`
Resource entities (kind=environment) are present in
`entities/catalog-info.yaml`. The `EnvironmentPicker` reads them to
populate the env dropdown for each scaffolder run.

---

## Open items (not in original PENDING_TASKS but worth noting)

- **ZoneAssociation upjet bug** — second non-inline VPC association
  on a private zone trips a known upjet "empty result" failure. AWS
  state ends up correct (manually verified); the MR's `Ready` condition
  stays `Creating` due to a deeper Crossplane runtime gap that the
  recoverer's annotation-patching can't break out of. Worth filing
  upstream alongside `crossplane-contrib/provider-upjet-aws#1806`.

- **Cross-account VPC association** — `private-cross-account-vpc`
  scenario in `zone-scenarios.py` not exercised. Would compound the
  multi-VPC ZA bug above; defer until upstream fix.
