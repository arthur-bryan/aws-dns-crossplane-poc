import TextField from '@material-ui/core/TextField';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { useEffect, useRef } from 'react';

import { getParentFormDataFromId } from '../utils';

// Plain schema-only number fields under `dependencies.oneOf` only ever get
// unmounted when the branch is switched away from -- RJSF does not clear
// their prior value out of formData when that happens, so a record's last
// weight silently lingers (and shows up on the Review step) even after the
// user turns weighted routing back off. This field clears itself on unmount,
// guarded so a whole record row being *removed* (rather than just toggled)
// never fires a stale write into whatever now occupies that array slot --
// see the unmount handler below for how that's distinguished.
export const WeightedWeightField = (props: FieldExtensionComponentProps<number>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const latestRef = useRef({ formContextFormData: (formContext as any)?.formData, idSchemaId: idSchema?.$id, onChange });
  useEffect(() => {
    latestRef.current = { formContextFormData: (formContext as any)?.formData, idSchemaId: idSchema?.$id, onChange };
  });

  useEffect(() => {
    return () => {
      const { formContextFormData, idSchemaId, onChange: latestOnChange } = latestRef.current;
      const record = getParentFormDataFromId(formContextFormData, idSchemaId) as Record<string, any> | undefined;
      // Only clear if this array slot still exists and genuinely toggled weighted
      // routing off -- if the whole row was removed instead, the last snapshot this
      // component saw still has enableWeightedRouting: true, so we correctly skip.
      if (record && record.enableWeightedRouting === false) {
        latestOnChange(undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The displayed default (schema.default) is only a placeholder until it's actually
  // written into formData -- otherwise submitting without touching this field leaves
  // weight unset even though "100" was visibly shown.
  useEffect(() => {
    if (formData === undefined && typeof schema.default === 'number') {
      onChange(schema.default);
    }
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
