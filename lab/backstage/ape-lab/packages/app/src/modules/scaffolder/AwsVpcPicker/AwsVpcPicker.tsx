import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import Chip from '@material-ui/core/Chip';
import FormHelperText from '@material-ui/core/FormHelperText';
import TextField from '@material-ui/core/TextField';
import Autocomplete from '@material-ui/lab/Autocomplete';
import { useEffect } from 'react';
import useAsync from 'react-use/esm/useAsync';

import { AwsVpcPickerProps } from './schema';

type Vpc = {
  id: string;
  region: string;
  cidrBlock?: string;
  isDefault: boolean;
  tags?: Record<string, string>;
};

type SelectedVpc = { vpcId: string; vpcRegion: string };

function getVpcLabel(vpc: Vpc): string {
  const name = vpc.tags?.Name;
  const cidr = vpc.cidrBlock ? ` - ${vpc.cidrBlock}` : '';
  const defaultLabel = vpc.isDefault ? ' [default]' : '';
  return `${name ? `${name} (${vpc.id})` : vpc.id}${cidr}${defaultLabel}`;
}

export const AwsVpcPicker = (props: AwsVpcPickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);

  const uiOptions = uiSchema['ui:options'] ?? {};
  const environmentFieldName = uiOptions.environmentFieldName;
  const environmentFromForm = environmentFieldName ? formContext?.formData?.[environmentFieldName] : undefined;
  const rawEnvironment = uiOptions.environment ?? environmentFromForm;
  const environment = typeof rawEnvironment === 'string' && rawEnvironment.trim().length > 0 ? rawEnvironment : undefined;
  const excludeDefault = uiOptions.excludeDefault ?? false;

  const selectedVpcs = Array.isArray(formData) ? (formData as SelectedVpc[]) : [];

  const {
    value: fetchedVpcs = [],
    loading,
    error,
  } = useAsync(async () => {
    if (!environment) {
      return [] as Vpc[];
    }
    const baseUrl = await discoveryApi.getBaseUrl('aws');
    const response = await fetchApi.fetch(`${baseUrl}/dns-vpcs?environment=${encodeURIComponent(environment)}`);

    if (!response.ok) {
      throw new Error(`Failed to load AWS VPCs (${response.status})`);
    }

    const data = (await response.json()) as { vpcs?: Vpc[] };
    return data.vpcs ?? [];
  }, [discoveryApi, fetchApi, environment]);

  const vpcs = excludeDefault ? fetchedVpcs.filter((v) => !v.isDefault) : fetchedVpcs;

  useEffect(() => {
    if (selectedVpcs.length > 0 && vpcs.length > 0) {
      const validIds = new Set(vpcs.map((v) => v.id));
      const filtered = selectedVpcs.filter((v) => validIds.has(v.vpcId));
      if (filtered.length !== selectedVpcs.length) {
        onChange(filtered.length > 0 ? filtered : undefined);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vpcs]);

  let helperText = 'Select an environment first to load AWS VPCs.';

  if (loading) {
    helperText = 'Loading VPCs...';
  } else if (error) {
    helperText = 'Could not load AWS VPCs.';
  } else if (environment) {
    helperText = vpcs.length > 0 ? `${vpcs.length} VPC(s) available for ${environment}.` : `No VPCs found for ${environment}.`;
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
          multiple
          id={idSchema?.$id}
          disabled={disabled || loading || !environment}
          loading={loading}
          options={vpcs}
          getOptionLabel={(vpc) => getVpcLabel(vpc)}
          getOptionSelected={(option, val) => option.id === val.id}
          value={vpcs.filter((v) => selectedVpcs.some((s) => s.vpcId === v.id))}
          onChange={(_, selected) =>
            onChange(
              selected.length > 0
                ? selected.map((v) => ({ vpcId: v.id, vpcRegion: v.region }))
                : undefined,
            )
          }
          renderTags={(value, getTagProps) =>
            value.map((vpc, index) => <Chip label={getVpcLabel(vpc)} {...getTagProps({ index })} key={vpc.id} />)
          }
          renderOption={(vpc) => getVpcLabel(vpc)}
          renderInput={(params) => (
            <TextField {...params} label={schema.title ?? 'AWS VPCs'} margin="dense" variant="outlined" required={required} fullWidth />
          )}
        />
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
