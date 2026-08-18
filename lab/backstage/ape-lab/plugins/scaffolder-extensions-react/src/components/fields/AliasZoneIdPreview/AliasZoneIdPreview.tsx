import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import FormHelperText from '@material-ui/core/FormHelperText';
import TextField from '@material-ui/core/TextField';

import { getParentFormDataFromId } from '../utils';
import { resolveAliasZoneId } from '../aliasZoneIds';

// Read-only preview of the Route53 hosted-zone-ID the platform will actually resolve
// for this alias target, mirroring the composition's lookup table exactly (see
// aliasZoneIds.ts). Exists so a user (or we, while testing) can catch a bad
// serviceType/region combination -- one that resolves to nothing -- before submitting,
// instead of discovering it only after the record gets stuck in ReconcileError.
export const AliasZoneIdPreview = (props: FieldExtensionComponentProps<string>) => {
  const { formContext, idSchema } = props;
  const rootFormData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const record = (getParentFormDataFromId(rootFormData, idSchema?.$id) ?? rootFormData) as Record<string, any>;

  if (record.type !== 'ALIAS') {
    return null;
  }

  const serviceType = record.serviceType as string | undefined;
  const region = record.region as string | undefined;
  const customZoneId = record.customZoneId as string | undefined;

  if (!serviceType) {
    return null;
  }

  const zoneId = resolveAliasZoneId(serviceType, region, customZoneId);

  // For every service type except Custom, the region picker only ever offers options
  // from this same resolution table (see AliasRegionField), so an empty result here
  // should be unreachable through the UI -- this branch is a defense-in-depth message
  // for a non-UI submission, not something a normal user should ever see. Custom is
  // different: customZoneId is free text the user is expected to type, so "not filled
  // in yet" is a normal, expected transient state, not a bad combination.
  const isCustomNotYetTyped = serviceType === 'Custom' && !zoneId;

  return (
    <ScaffolderField required={false} disabled>
      <TextField
        id={idSchema?.$id}
        label="Resolved Alias Zone ID (preview)"
        value={zoneId || (isCustomNotYetTyped ? '(enter a hosted zone ID above)' : '(none -- this combination will fail)')}
        error={!zoneId && !isCustomNotYetTyped}
        disabled
        margin="dense"
        variant="outlined"
        fullWidth
      />
      <FormHelperText error={!zoneId && !isCustomNotYetTyped}>
        {zoneId
          ? 'This is the AWS hosted zone ID the platform will write for this alias target.'
          : isCustomNotYetTyped
            ? 'Enter the custom hosted zone ID above to see it previewed here.'
            : 'No zone ID resolves for this service type + region combination -- submitting this will get stuck in ReconcileError. Pick a different region or service type.'}
      </FormHelperText>
    </ScaffolderField>
  );
};
