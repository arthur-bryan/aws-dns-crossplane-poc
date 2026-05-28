import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import TextField from '@material-ui/core/TextField';
import Autocomplete from '@material-ui/lab/Autocomplete';
import { useEffect } from 'react';
import useAsync from 'react-use/esm/useAsync';

import { AwsDnsZonePickerProps } from './schema';

type Zone = {
  id: string;
  name: string;
  private: boolean;
  recordCount?: number;
};

function isEnvironment(value: unknown): boolean {
  return typeof value === 'string' && value.trim().length > 0;
}

export const AwsDnsZonePicker = (props: AwsDnsZonePickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);

  const uiOptions = (uiSchema?.['ui:options'] ?? {}) as Record<string, any>;
  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const environmentFromForm = formContext?.formData?.[environmentFieldName];
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const environment = typeof rawEnvironment === 'string' ? rawEnvironment : undefined;
  const zoneValue = formData && typeof formData === 'object' ? (formData as { id: string; name: string }) : undefined;

  const {
    value: zones = [],
    loading,
    error,
  } = useAsync(async () => {
    if (!environment || typeof environment !== 'string' || environment.trim().length === 0) {
      return [] as Zone[];
    }

    const baseUrl = await discoveryApi.getBaseUrl('aws');
    const response = await fetchApi.fetch(`${baseUrl}/dns-zones?environment=${encodeURIComponent(environment)}`);

    if (!response.ok) {
      throw new Error(`Failed to load DNS zones (${response.status})`);
    }

    const data = (await response.json()) as { zones?: Zone[] };
    return data.zones ?? [];
  }, [discoveryApi, fetchApi, environment]);

  useEffect(() => {
    if (zoneValue && zones.length > 0 && !zones.some((zone) => zone.id === zoneValue.id)) {
      onChange(undefined);
    }
  }, [zones, zoneValue, onChange]);

  let helperText = 'Select an environment first to load DNS zones.';

  if (loading) {
    helperText = 'Loading DNS zones...';
  } else if (error) {
    helperText = 'Could not load DNS zones.';
  } else if (isEnvironment(environment)) {
    helperText = zones.length > 0 ? `${zones.length} zone(s) available for ${environment}.` : `No DNS zones found for ${environment}.`;
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
          disabled={disabled || loading || !isEnvironment(environment)}
          loading={loading}
          options={zones}
          getOptionLabel={(zone) => zone.name}
          getOptionSelected={(option, val) => option.id === val.id}
          value={zones.find((zone) => zone.id === zoneValue?.id) ?? null}
          onChange={(_, selected) => onChange(selected ? { id: selected.id, name: selected.name } : undefined)}
          renderOption={(zone) => zone.name}
          renderInput={(params) => (
            <TextField {...params} label={schema.title ?? 'DNS Zone'} margin="dense" variant="outlined" required={required} fullWidth />
          )}
        />
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
