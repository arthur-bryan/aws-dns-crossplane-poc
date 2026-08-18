import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import FormHelperText from '@material-ui/core/FormHelperText';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import { useEffect } from 'react';

import { getParentFormDataFromId } from '../utils';
import { isGlobalServiceType, isRegionalServiceType, regionsForServiceType } from '../aliasZoneIds';

// Declared as a single top-level field (not nested per-serviceType oneOf branch, unlike
// the schema's first draft) specifically to avoid the same class of bug fixed earlier for
// weight/setIdentifier: a value left over from one oneOf branch failing the next branch's
// stricter enum and blocking form submission. One field, one component, self-correcting.
export const AliasRegionField = (props: FieldExtensionComponentProps<string>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const rootFormData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const record = (getParentFormDataFromId(rootFormData, idSchema?.$id) ?? {}) as Record<string, any>;
  const serviceType = record.serviceType as string | undefined;

  const global = isGlobalServiceType(serviceType);
  const regional = isRegionalServiceType(serviceType);
  const options = regionsForServiceType(serviceType);

  useEffect(() => {
    if (global) {
      if (formData !== 'global') onChange('global');
    } else if (regional) {
      // Never leave this on an unresolvable value -- the dropdown only ever offers
      // options from the same table AliasZoneIdPreview resolves against, so falling
      // back to the first one the moment serviceType lands here (or changes to a
      // service whose table doesn't include the current region) guarantees the
      // preview always shows a real zone ID, never "no zone ID resolves".
      if (!formData || !options.includes(formData)) onChange(options[0]);
    } else if (formData !== undefined) {
      onChange(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceType, global, regional]);

  if (!serviceType || (!global && !regional)) {
    return null;
  }

  return (
    <ScaffolderField
      rawErrors={rawErrors}
      required={required}
      disabled={disabled}
      errors={errors}
    >
      <>
        <TextField
          id={idSchema?.$id}
          select
          label={schema.title ?? 'Region'}
          margin="dense"
          variant="outlined"
          required={required}
          fullWidth
          value={global ? 'global' : formData ?? ''}
          disabled={disabled || global}
          onChange={event => onChange(event.target.value)}
        >
          {global ? (
            <MenuItem value="global">global</MenuItem>
          ) : (
            options.map(region => (
              <MenuItem key={region} value={region}>
                {region}
              </MenuItem>
            ))
          )}
        </TextField>
        <FormHelperText>
          {global
            ? 'This service type uses a single global endpoint -- no region needed.'
            : (uiSchema['ui:help'] ?? schema.description ?? 'AWS region this resource is deployed in.')}
        </FormHelperText>
      </>
    </ScaffolderField>
  );
};
