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
  accountName?: string;
  environment?: string;
};

export const AwsDnsZonePicker = (props: AwsDnsZonePickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);

  const uiOptions = uiSchema['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName;
  const environmentFromForm = environmentFieldName ? formContext?.formData?.[environmentFieldName] : undefined;
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const environment = typeof rawEnvironment === 'string' && rawEnvironment.trim().length > 0 ? rawEnvironment : undefined;
  // When set, this picker is choosing a *parent* zone to delegate from, not a
  // same-environment zone -- delegation hierarchy: dev/hml may delegate from
  // their own environment or from prd; prd may only delegate from prd; dev
  // and hml may never delegate from each other.
  const restrictParentEnvironments = uiOptions.restrictParentEnvironments === true;
  const zoneValue = formData && typeof formData === 'object' ? (formData as Zone) : undefined;

  const {
    value: fetchedZones = [],
    loading,
    error,
  } = useAsync(async () => {
    const baseUrl = await discoveryApi.getBaseUrl('aws');
    const url = environment && !restrictParentEnvironments
      ? `${baseUrl}/dns-zones?environment=${encodeURIComponent(environment)}`
      : `${baseUrl}/dns-zones`;
    const response = await fetchApi.fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to load DNS zones (${response.status})`);
    }

    const data = (await response.json()) as { zones?: Zone[] };
    return data.zones ?? [];
  }, [discoveryApi, fetchApi, environment, restrictParentEnvironments]);

  const zones = restrictParentEnvironments && environment
    ? fetchedZones.filter((zone) => zone.environment === environment || zone.environment === 'prd')
    : fetchedZones;

  useEffect(() => {
    if (zoneValue && zones.length > 0 && !zones.some((zone) => zone.id === zoneValue.id)) {
      onChange(undefined);
    }
  }, [zones, zoneValue, onChange]);

  let helperText: string;
  if (loading) {
    helperText = 'Loading DNS zones...';
  } else if (error) {
    helperText = 'Could not load DNS zones.';
  } else {
    helperText = zones.length > 0
      ? `${zones.length} zone(s) available${environment ? ` for ${environment}` : ''}.`
      : `No DNS zones found${environment ? ` for ${environment}` : ''}.`;
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
          disabled={disabled || loading}
          loading={loading}
          options={zones}
          getOptionLabel={(zone) => zone.name}
          getOptionSelected={(option, val) => option.id === val.id}
          value={zones.find((zone) => zone.id === zoneValue?.id) ?? null}
          onChange={(_, selected) => onChange(selected ? { id: selected.id, name: selected.name, accountName: selected.accountName, environment: selected.environment } : undefined)}
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
