import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
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

  const uiOptions = uiSchema['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const zoneFieldName = uiOptions.zoneFieldName ?? 'zoneId';
  const environmentFromForm = formContext?.formData?.[environmentFieldName];
  const zoneFromForm = formContext?.formData?.[zoneFieldName];
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const rawZoneId = uiOptions.zoneId ?? zoneFromForm;
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

    const baseUrl = await discoveryApi.getBaseUrl('dns');
    const response = await fetchApi.fetch(`${baseUrl}/records?environment=${encodeURIComponent(environment)}&zoneId=${encodeURIComponent(zoneId)}`);

    if (!response.ok) {
      throw new Error(`Failed to load DNS records (${response.status})`);
    }

    const data = (await response.json()) as { records?: DnsRecord[] };
    return data.records ?? [];
  }, [discoveryApi, fetchApi, environment, zoneId]);

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
