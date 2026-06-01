import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import Autocomplete from '@material-ui/lab/Autocomplete';
import { useEffect } from 'react';
import useAsync from 'react-use/esm/useAsync';

import { AwsDnsRecordPickerProps } from './schema';

type DnsRecord = {
  name: string;
  type: string;
  ttl?: number;
  values: string[];
  aliasTarget?: {
    dnsName: string;
    hostedZoneId: string;
    evaluateTargetHealth: boolean;
  };
  setIdentifier?: string;
  weight?: number;
};

export const AwsDnsRecordPicker = (props: AwsDnsRecordPickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const catalogApi = useApi(catalogApiRef);

  const uiOptions = uiSchema['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const zoneFieldName = uiOptions.zoneFieldName ?? 'zoneId';
  const environmentFromForm = formContext?.formData?.[environmentFieldName];
  const zoneFromForm = formContext?.formData?.[zoneFieldName];
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const rawZoneId = uiOptions.zoneId ?? (zoneFromForm && typeof zoneFromForm === 'object' ? (zoneFromForm as { id: string }).id : zoneFromForm);
  const zoneName = zoneFromForm && typeof zoneFromForm === 'object' ? (zoneFromForm as { name?: string }).name : undefined;
  const environment = typeof rawEnvironment === 'string' ? rawEnvironment : undefined;
  const zoneId = typeof rawZoneId === 'string' ? rawZoneId : undefined;

  const {
    value: records = [],
    loading,
    error,
  } = useAsync(async () => {
    if (!environment || !zoneId) {
      return [] as DnsRecord[];
    }

    const baseUrl = await discoveryApi.getBaseUrl('aws');
    const response = await fetchApi.fetch(
      `${baseUrl}/dns-records?environment=${encodeURIComponent(environment)}&zoneId=${encodeURIComponent(zoneId)}`,
    );

    if (!response.ok) {
      throw new Error(`Failed to load DNS records (${response.status})`);
    }

    const data = (await response.json()) as { records?: DnsRecord[] };
    const liveRecords = data.records ?? [];

    // Exclude records already onboarded into the platform: a record can only be
    // claimed once. Onboarded records exist as catalog Resource entities named
    // `record-<fqdn>`. Build an exclusion set of "<fqdn>|<type>" (lower-cased,
    // trailing dot stripped) and drop any live record that matches.
    const { items: managed } = await catalogApi.getEntities({
      filter: [{ kind: 'resource', 'spec.type': 'Record' }, { kind: 'resource', 'spec.type': 'aws-dns-record' }],
      fields: ['metadata.name', 'metadata.annotations', 'spec.recordType', 'spec.recordName', 'spec.zoneName'],
    });
    const norm = (s?: string) => (s ?? '').replace(/\.$/, '').toLowerCase();
    const onboarded = new Set<string>();
    for (const e of managed) {
      const ann = (e.metadata.annotations ?? {}) as Record<string, string>;
      const spec = (e.spec ?? {}) as Record<string, any>;
      // FQDN can come from (priority): record-fqdn annotation (lab shape),
      // spec.recordName + spec.zoneName (APE shape, with defensive handling
      // for templates that wrote the FQDN as recordName), or entity name
      // `record-<fqdn>` (legacy lab naming).
      let fqdn = norm(ann['dock.tech/record-fqdn']);
      if (!fqdn && spec.zoneName) {
        const rn = norm(spec.recordName);
        const zn = norm(spec.zoneName);
        if (!rn || rn === zn) {
          fqdn = zn; // apex
        } else if (rn.endsWith('.' + zn)) {
          fqdn = rn; // recordName already carried the full FQDN
        } else {
          fqdn = `${rn}.${zn}`;
        }
      }
      if (!fqdn && e.metadata.name.startsWith('record-')) {
        fqdn = norm(e.metadata.name.slice('record-'.length));
      }
      if (!fqdn) continue;
      const rtype = (ann['dock.tech/record-type'] || spec.recordType || '').toString().toUpperCase();
      onboarded.add(`${fqdn}|${rtype}`);
      // ALIAS records are surfaced by Route53 as type A or AAAA (the AliasTarget
      // attaches to the A/AAAA RRset). Add those equivalents so we still match.
      if (rtype === 'ALIAS') {
        onboarded.add(`${fqdn}|A`);
        onboarded.add(`${fqdn}|AAAA`);
      }
    }

    return liveRecords.filter(r => !onboarded.has(`${norm(r.name)}|${(r.type ?? '').toUpperCase()}`));
  }, [discoveryApi, fetchApi, catalogApi, environment, zoneId, zoneName]);

  useEffect(() => {
    if (formData && records.length > 0 && !records.some((r) => r.name === formData.name && r.type === formData.type)) {
      onChange(undefined);
    }
  }, [records, formData, onChange]);

  let helperText = 'Select a zone first to load DNS records.';

  if (loading) {
    helperText = 'Loading DNS records...';
  } else if (error) {
    helperText = 'Could not load DNS records.';
  } else if (environment && zoneId) {
    helperText = records.length > 0 ? `${records.length} claimable record(s) — type to filter.` : 'No claimable records found in this zone.';
  }

  return (
    <ScaffolderField
      rawErrors={rawErrors}
      rawDescription={uiSchema['ui:description'] ?? schema.description}
      required={required}
      disabled={disabled}
      errors={errors}
    >
      <>
        <Autocomplete
          id={idSchema?.$id}
          disabled={disabled || loading || !environment || !zoneId}
          loading={loading}
          options={records}
          getOptionLabel={(r) => `${r.name} (${r.type})`}
          getOptionSelected={(a, b) => a.name === b.name && a.type === b.type}
          value={records.find((r) => r.name === formData?.name && r.type === formData?.type) ?? null}
          onChange={(_, selected) => onChange(selected ?? undefined)}
          filterOptions={(options, state) => {
            const input = state.inputValue.toLowerCase();
            return options.filter((r) => r.name.toLowerCase().includes(input) || r.type.toLowerCase().includes(input));
          }}
          renderOption={(r) => (
            <MenuItem key={`${r.name}-${r.type}`}>
              {r.name} ({r.type})
            </MenuItem>
          )}
          renderInput={(params) => (
            <TextField {...params} label={schema.title ?? 'DNS Record'} margin="dense" variant="outlined" required={required} fullWidth />
          )}
        />
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
