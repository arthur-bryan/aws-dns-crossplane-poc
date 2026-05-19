import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import TextField from '@material-ui/core/TextField';
import Autocomplete from '@material-ui/lab/Autocomplete';
import { useEffect } from 'react';
import useAsync from 'react-use/esm/useAsync';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

type Zone = {
  id: string;
  name: string;
  private: boolean;
  recordCount?: number;
};

export const AwsDnsZonePicker = (
  props: FieldExtensionComponentProps<string>,
) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);

  const uiOptions = (uiSchema as any)['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const environmentFromForm = formContext?.formData?.[environmentFieldName];
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const environment = typeof rawEnvironment === 'string' ? rawEnvironment : undefined;
  const zoneValue = typeof formData === 'string' ? formData : '';

  const {
    value: zones = [],
    loading,
    error,
  } = useAsync(async () => {
    if (!environment || environment.trim().length === 0) {
      return [] as Zone[];
    }

    const baseUrl = await discoveryApi.getBaseUrl('dns');
    const response = await fetchApi.fetch(
      `${baseUrl}/zones?environment=${encodeURIComponent(environment)}`,
    );

    if (!response.ok) {
      throw new Error(`Failed to load DNS zones (${response.status})`);
    }

    const data = (await response.json()) as { zones?: Zone[] };
    return data.zones ?? [];
  }, [discoveryApi, fetchApi, environment]);

  useEffect(() => {
    if (zoneValue && zones.length > 0 && !zones.some(z => z.id === zoneValue)) {
      onChange(undefined);
    }
  }, [zones, zoneValue, onChange]);

  let helperText = 'Select an environment first to load DNS zones.';
  if (loading) {
    helperText = 'Loading DNS zones...';
  } else if (error) {
    helperText = 'Could not load DNS zones.';
  } else if (environment) {
    helperText =
      zones.length > 0
        ? `${zones.length} zone(s) available for ${environment}.`
        : `No DNS zones found for ${environment}.`;
  }

  return (
    <ScaffolderField
      rawErrors={rawErrors}
      rawDescription={(uiSchema as any)['ui:description'] ?? schema.description}
      required={required}
      disabled={disabled}
      errors={errors}
    >
      <>
        <Autocomplete
          id={idSchema?.$id}
          disabled={disabled || loading || !environment}
          loading={loading}
          options={zones}
          getOptionLabel={zone => zone.name}
          getOptionSelected={(option, val) => option.id === val.id}
          value={zones.find(z => z.id === zoneValue) ?? null}
          onChange={(_, selected) => onChange(selected ? selected.id : undefined)}
          renderInput={params => (
            <TextField
              {...params}
              label={schema.title ?? 'DNS Zone'}
              margin="dense"
              variant="outlined"
              required={required}
              fullWidth
            />
          )}
        />
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
