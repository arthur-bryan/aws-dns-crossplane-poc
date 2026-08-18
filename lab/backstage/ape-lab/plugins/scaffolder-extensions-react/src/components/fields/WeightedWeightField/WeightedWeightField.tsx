import TextField from '@material-ui/core/TextField';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { useEffect } from 'react';

import { getParentFormDataFromId } from '../utils';

// Declared in BOTH branches of the enableWeightedRouting oneOf (see record.yaml) so this
// field stays mounted across the toggle instead of unmounting -- a field that only exists
// in the "true" branch unmounts the instant the box is unchecked, and React never gives it
// a render with the post-toggle sibling value first, so it has no reliable way to tell a
// genuine toggle-off apart from the whole record row being removed. Staying mounted sidesteps
// that entirely: this component always sees the current enableWeightedRouting value on every
// render and clears itself the moment it goes false.
export const WeightedWeightField = (props: FieldExtensionComponentProps<number>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const rootFormData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const record = (getParentFormDataFromId(rootFormData, idSchema?.$id) ?? {}) as Record<string, any>;
  const weighted = record.enableWeightedRouting === true;

  useEffect(() => {
    if (!weighted) {
      // Wait for the sibling SetIdentifier field to clear itself first. RJSF's per-field
      // onChange merges against a snapshot of the parent record object -- two sibling
      // fields both clearing in the same render tick race each other, and whichever
      // commits second clobbers the first back in with a stale snapshot. Gating on
      // setIdentifier already being gone sequences the two clears instead of racing them.
      if (formData !== undefined && record.setIdentifier === undefined) {
        onChange(undefined);
      }
    } else if (formData === undefined && typeof schema.default === 'number') {
      // Displaying the schema default is only a placeholder until it's actually written into
      // formData -- otherwise a never-touched weight field submits undefined instead of 100.
      onChange(schema.default);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weighted, record.setIdentifier, formData]);

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
        type="number"
        label={schema.title ?? 'Weight'}
        value={formData ?? schema.default ?? ''}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(raw === '' ? undefined : Number(raw));
        }}
        margin="dense"
        variant="outlined"
        required={required}
        fullWidth
        inputProps={{ min: schema.minimum, max: schema.maximum }}
        helperText={uiSchema['ui:help'] ?? schema.description}
      />
    </ScaffolderField>
  );
};
