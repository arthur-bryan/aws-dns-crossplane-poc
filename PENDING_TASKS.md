## Pending Tasks — DNS Lab Readiness

### TASK-1: Create IAM role in each DNS account for Backstage

**Who:** AWS admin (you)
**Accounts:** all 3 DNS accounts (dev, hml, prd)
**What to create:** IAM role named `backstage-role` in each account

Trust policy — allow the account running Backstage (your personal/admin account) to assume it:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<YOUR-ADMIN-ACCOUNT-ID>:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Permission policy — read-only Route53:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "route53:ListHostedZones",
        "route53:ListHostedZonesByName",
        "route53:ListResourceRecordSets",
        "route53:GetHostedZone"
      ],
      "Resource": "*"
    }
  ]
}
```

After creating the roles, note the ARNs:
- `arn:aws:iam::<dev-account-id>:role/backstage-role`
- `arn:aws:iam::<hml-account-id>:role/backstage-role`
- `arn:aws:iam::<prd-account-id>:role/backstage-role`

---

### TASK-2: Set env vars and populate app-config.local.yaml

Before running `make backstage-up`, export these in your shell (or add to `~/.bashrc`):

```bash
export DNS_ACCOUNT_ID_DEV=<dev-dns-account-id>
export DNS_ROLE_ARN_DEV=arn:aws:iam::<dev-dns-account-id>:role/backstage-role

export DNS_ACCOUNT_ID_HML=<hml-dns-account-id>
export DNS_ROLE_ARN_HML=arn:aws:iam::<hml-dns-account-id>:role/backstage-role

export DNS_ACCOUNT_ID_PRD=<prd-dns-account-id>
export DNS_ROLE_ARN_PRD=arn:aws:iam::<prd-dns-account-id>:role/backstage-role

export GITHUB_TOKEN=<your-github-pat>
```

The `backstage-up.sh` script copies `lab/backstage/app-config.example.yaml` to
`lab/backstage/ape-lab/app-config.local.yaml` on first run. The env vars above
are substituted at runtime by Backstage's config loader.

If `app-config.local.yaml` already exists (from a previous run), replace the `dns:` block:
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

### TASK-3: Install new npm dependencies

After pulling this branch, run `yarn install` in the Backstage app directory.
New packages added: `@aws-sdk/client-route-53`, `@aws-sdk/credential-providers`,
`express`, `@types/express` (backend), `@material-ui/lab` (frontend).

```bash
cd lab/backstage/ape-lab
yarn install
```

---

### TASK-4: Verify local AWS credentials can assume the DNS roles

The Backstage backend uses the **default AWS credential chain** as the base
credential before assuming the `backstage-role` in each DNS account.
On your local PC this means `~/.aws/credentials` or env vars.

Test that assumption works:
```bash
# Replace with your actual account ID and profile
aws sts assume-role \
  --role-arn arn:aws:iam::<dns-account-id>:role/backstage-role \
  --role-session-name backstage-test \
  --profile <your-admin-profile>
```

If this succeeds you will see temporary credentials in the output.
If it fails with `AccessDenied`, check the trust policy on the role (TASK-1).

---

### TASK-5: Test the zone and record pickers end-to-end

1. Start the lab: `make -C lab up && make -C lab backstage-up`
2. Open http://localhost:3000
3. Go to Create → use any template with `EnvironmentPicker` field
4. Verify `EnvironmentPicker` loads environments from the System entity `spec.environments`
5. Verify `AwsDnsZonePicker` loads zones from Route53 when environment is selected
6. Verify `AwsDnsRecordPicker` loads records when a zone is selected

**Backend endpoints to test manually:**
```bash
# Should return JSON list of zones
curl "http://localhost:7007/api/dns/zones?environment=prd"

# Should return JSON list of records
curl "http://localhost:7007/api/dns/records?environment=prd&zoneId=<zone-id>"
```

**Implementation notes:**
- `EnvironmentPicker`: reads environments from the System catalog entity `spec.environments` (no backend call).
  Looks up the form field named by `ui:options.systemFieldName` (default `system`) for the entity ref.
- `AwsDnsZonePicker`: calls `GET /api/dns/zones?environment=X`, reads env from field named by
  `ui:options.environmentFieldName` (default `environment`).
- `AwsDnsRecordPicker`: calls `GET /api/dns/records?environment=X&zoneId=Y`, reads zone from field named by
  `ui:options.zoneFieldName` (default `zoneId`).
- All three components use `ScaffolderField` wrapper and `useAsync` from `react-use` — exact same pattern
  as APE's `AwsAccountPicker`.

---

### TASK-6: Wire AwsDnsZonePicker into the claim template

File: `backstage-templates/templates/resources/aws/record-claim.yaml`

The claim template currently uses `EntityPicker` for zone selection (catalog-only).
Once TASK-1–5 are validated, update the zone field to use `AwsDnsZonePicker`:

```yaml
zoneId:
  title: DNS Zone
  type: string
  description: Select the zone from Route53
  ui:field: AwsDnsZonePicker
  ui:options:
    environmentFieldName: environment
```

The `environment` field must appear before `zoneId` in the form and use `EnvironmentPicker`.
The `zoneId` returned by the picker is the Route53 hosted zone ID (e.g. `Z03010981ALJFZB4QLU8W`).
Pass it into the written entity as `spec.zoneId` so the composition can use `Observe` policy.

---

### TASK-7: Add AwsDnsRecordPicker to the claim template

After TASK-6 works, add `AwsDnsRecordPicker` to auto-fill record details
when user selects an existing record from the live Route53 list.

```yaml
existingRecord:
  title: Existing Record
  type: object
  description: Select the record to claim from Route53
  ui:field: AwsDnsRecordPicker
  ui:options:
    environmentFieldName: environment
    zoneFieldName: zoneId
```

The picker returns the full record object: `{ name, type, ttl, values, aliasTarget }`.
Use `parameters.existingRecord.name`, `parameters.existingRecord.type`, etc.
in the written entity YAML to pre-populate fields (user only confirms ownership).

---

### TASK-8: Add hml environment to provider-config

File: `lab/provider-config/`

Currently only `dev-account.yaml` and `prd-account.yaml` exist.
If hml has its own DNS account, add `hml-account.yaml` following the same pattern.

---

### TASK-9: Validate compositions handle import.existing for records

The `dock.tech/import-existing: "true"` annotation on claimed records
should trigger `[Observe, Update]` management policy in the Record composition.

Verify in `crossplane-compositions-dns/templates/record.yaml` that:
- When `spec.import.existing == true`, the MR uses `managementPolicies: [Observe, Update]`
- The composition does NOT attempt to create the record in Route53
- The composition reads back the current Route53 state and syncs it to XR status

---

### TASK-10: Ensure System entities have spec.environments populated

The `EnvironmentPicker` reads `spec.environments` from the selected System entity in the catalog.
For the picker to work, each System entity YAML must have the environments block, e.g.:

```yaml
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: dns
  namespace: default
spec:
  owner: group:default/platform
  domain: dns
  environments:
    - name: dev
      aws:
        account: "<dev-account-id>"
        accountName: dns-dev
    - name: hml
      aws:
        account: "<hml-account-id>"
        accountName: dns-hml
    - name: prd
      aws:
        account: "<prd-account-id>"
        accountName: dns-prd
```

Check `entities/` for existing System entities and add `spec.environments` if missing.
This is the same catalog structure APE uses — the picker depends on it.
