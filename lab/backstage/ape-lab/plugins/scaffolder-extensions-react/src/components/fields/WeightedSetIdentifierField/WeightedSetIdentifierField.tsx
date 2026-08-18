import TextField from '@material-ui/core/TextField';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { useEffect, useRef } from 'react';

import { getParentFormDataFromId } from '../utils';

// See WeightedWeightField -- same self-clearing-on-unmount fix, for the
// SetIdentifier text field that sits alongside it under the same
// `dependencies.enableWeightedRouting.oneOf` branch.
export const WeightedSetIdentifierField = (props: FieldExtensionComponentProps<string>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const latestRef = useRef({ formContextFormData: (formContext as any)?.formData, idSchemaId: idSchema?.$id, onChange });
  useEffect(() => {
    latestRef.current = { formContextFormData: (formContext as any)?.formData, idSchemaId: idSchema?.$id, onChange };
  });

  useEffect(() => {
    return () => {
      const { formContextFormData, idSchemaId, onChange: latestOnChange } = latestRef.current;
      const record = getParentFormDataFromId(formContextFormData, idSchemaId) as Record<string, any> | undefined;
      if (record && record.enableWeightedRouting === false) {
        latestOnChange(undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
