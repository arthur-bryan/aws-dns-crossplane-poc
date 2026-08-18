import TextField from '@material-ui/core/TextField';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { useEffect } from 'react';

import { getParentFormDataFromId } from '../utils';

// See WeightedWeightField -- same "stay mounted in both oneOf branches, clear on toggle-off"
// fix, for the SetIdentifier text field alongside it.
export const WeightedSetIdentifierField = (props: FieldExtensionComponentProps<string>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const rootFormData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const record = (getParentFormDataFromId(rootFormData, idSchema?.$id) ?? {}) as Record<string, any>;
  const weighted = record.enableWeightedRouting === true;

  useEffect(() => {
    if (!weighted && formData !== undefined) {
      onChange(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weighted]);

  if (!weighted) {
    return null;
  }

  return (
    <ScaffolderField
      rawErrors={rawErrors}
      rawDescription={uiSchema['ui:description'] ?? schema.description}
      required={required}
      disabled={disabled}
      errors={errors}
    >
      <TextField
        id={idSchema?.$id}
        label={schema.title ?? 'Set Identifier'}
        value={formData ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
        margin="dense"
        variant="outlined"
        required={required}
        fullWidth
        inputProps={{ minLength: schema.minLength, maxLength: schema.maxLength }}
        helperText={uiSchema['ui:help'] ?? schema.description}
      />
    </ScaffolderField>
  );
};
