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
import { resolveDependentFieldValue } from '../utils';

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
  weightPercent?: number;
};

const formatRecordLabel = (r: DnsRecord) =>
  r.setIdentifier
    ? `${r.name} (${r.type} · ${r.setIdentifier}: ${r.weightPercent ?? 0}%)`
    : `${r.name} (${r.type})`;

export const AwsDnsRecordPicker = (props: AwsDnsRecordPickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const catalogApi = useApi(catalogApiRef);

  const uiOptions = uiSchema['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const zoneFieldName = uiOptions.zoneFieldName ?? 'zoneId';
  const formValues = formContext?.formData;
  const environmentFromForm = resolveDependentFieldValue(formValues, idSchema?.$id, environmentFieldName);
  const zoneFromForm = resolveDependentFieldValue(formValues, idSchema?.$id, zoneFieldName);
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const rawZoneId = uiOptions.zoneId ?? (zoneFromForm && typeof zoneFromForm === 'object' ? (zoneFromForm as { id: string }).id : zoneFromForm);
  const environment = typeof rawEnvironment === 'string' ? rawEnvironment : undefined;
  const zoneId = typeof rawZoneId === 'string' ? rawZoneId : undefined;
  const excludeTypes = uiOptions.excludeTypes ?? [];
  const excludeClaimed = uiOptions.excludeClaimed ?? false;

  const {
    value: records = [],
    loading,
    error,
  } = useAsync(async () => {
    if (!environment || !zoneId) {
      return [] as DnsRecord[];
    }

    const baseUrl = await discoveryApi.getBaseUrl('aws');
    const response = await fetchApi.fetch(`${baseUrl}/dns-records?environment=${encodeURIComponent(environment)}&zoneId=${encodeURIComponent(zoneId)}`);

    if (!response.ok) {
      throw new Error(`Failed to load DNS records (${response.status})`);
    }

    const data = (await response.json()) as { records?: DnsRecord[] };
    const fetched = data.records ?? [];

    // Weight is only meaningful relative to its sibling weighted records (same name + type,
    // differing by SetIdentifier) -- compute the real Route53 traffic share here, against the
    // full unfiltered set, before excludeTypes/excludeClaimed can drop a sibling out of the sum.
    const weightSums = new Map<string, number>();
    for (const r of fetched) {
      if (r.setIdentifier && typeof r.weight === 'number') {
        const key = `${r.name}|${r.type}`;
        weightSums.set(key, (weightSums.get(key) ?? 0) + r.weight);
      }
    }
    let result = fetched.map((r) => {
      if (!r.setIdentifier || typeof r.weight !== 'number') {
        return r;
      }
      const sum = weightSums.get(`${r.name}|${r.type}`) ?? 0;
      return { ...r, weightPercent: sum > 0 ? Math.round((r.weight / sum) * 100) : 0 };
    });

    if (excludeTypes.length > 0) {
      const excluded = excludeTypes.map((t: string) => t.toUpperCase());
      result = result.filter((r) => !excluded.includes(r.type.toUpperCase()));
    }

    if (excludeClaimed) {
      const { items } = await catalogApi.getEntities({
        filter: { kind: 'Resource', 'spec.type': 'DNSRecord', 'metadata.labels.environment': environment },
        fields: ['spec.recordName', 'spec.zoneName', 'spec.setIdentifier'],
      });
      // Weighted records share one name -- multiple distinct Route53 record sets differing only by
      // SetIdentifier -- so the claimed-key must include it, or claiming one variant hides every
      // other (still-unclaimed) variant of the same name from this picker.
      const claimedKeys = new Set(
        items.map((e) => `${(e.spec as any)?.recordName ?? ''}|${(e.spec as any)?.zoneName ?? ''}|${(e.spec as any)?.setIdentifier ?? ''}`),
      );
      const zoneFromForm2 = formContext?.formData?.[zoneFieldName];
      const zoneName = typeof zoneFromForm2 === 'object' ? (zoneFromForm2 as { name: string }).name : zoneFromForm2 ?? '';
      const normalizedZone = String(zoneName).replace(/\.$/, '');
      result = result.filter((r) => {
        const fqdn = r.name.replace(/\.$/, '');
        const recordName = fqdn === normalizedZone ? '' : fqdn.replace(`.${normalizedZone}`, '');
        return !claimedKeys.has(`${recordName}|${normalizedZone}|${r.setIdentifier ?? ''}`);
      });
    }

    return result;
  }, [discoveryApi, fetchApi, catalogApi, environment, zoneId, excludeTypes, excludeClaimed]);

  useEffect(() => {
    if (formData && records.length > 0 && !records.some((r) => r.name === formData.name && r.type === formData.type && r.setIdentifier === formData.setIdentifier)) {
      onChange(undefined);
    }
  }, [records, formData, onChange]);

  let helperText = 'Select a zone first to load DNS records.';

  if (loading) {
    helperText = 'Loading DNS records...';
  } else if (error) {
    helperText = 'Could not load DNS records.';
  } else if (environment && zoneId) {
    helperText = records.length > 0 ? `${records.length} record(s) available. Type to filter.` : 'No records found in this zone.';
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
          getOptionLabel={formatRecordLabel}
          getOptionSelected={(a, b) => a.name === b.name && a.type === b.type && a.setIdentifier === b.setIdentifier}
          value={records.find((r) => r.name === formData?.name && r.type === formData?.type && r.setIdentifier === formData?.setIdentifier) ?? null}
          onChange={(_, selected) => onChange(selected ?? undefined)}
          filterOptions={(options, state) => {
            const input = state.inputValue.toLowerCase();
            return options.filter((r) => r.name.toLowerCase().includes(input) || r.type.toLowerCase().includes(input));
          }}
          renderOption={(r) => (
            <MenuItem key={`${r.name}-${r.type}-${r.setIdentifier ?? ''}`}>
              {formatRecordLabel(r)}
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
