import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import FormHelperText from '@material-ui/core/FormHelperText';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import { useEffect, useMemo } from 'react';

import { useEntityByRef } from '../../../hooks/useEntityByRef';

// Route53 normalizes ALIAS to record type A internally, so A <-> ALIAS is the
// only cross-type edit that doesn't force a Replace (destroy + recreate).
// Every other type is locked to itself -- see detectImmutableChanges in
// record-edit.yaml, which still owns the setIdentifier/weighted-toggle
// conditions this field doesn't touch.
const crossCompatible = (t: string): string[] => (t === 'A' || t === 'ALIAS' ? ['A', 'ALIAS'] : [t]);

export const RecordTypeField = (props: FieldExtensionComponentProps<string>) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const rootFormData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const entityRef = rootFormData.entityRef as string | undefined;
  const { entity, loading } = useEntityByRef({ entityRef });

  const existingType = (entity as any)?.spec?.recordType as string | undefined;
  const schemaEnum = useMemo(() => (Array.isArray(schema.enum) ? (schema.enum as string[]) : []), [schema.enum]);

  const allowedTypes = useMemo(() => {
    if (!existingType) {
      // Not resolved yet (or entityRef missing) -- don't offer an unsafe type
      // change before we know what's actually safe. Restrict to whatever is
      // already in formData so the field renders without flashing every option.
      return formData ? [formData] : schemaEnum;
    }
    return crossCompatible(existingType).filter(t => schemaEnum.includes(t));
  }, [existingType, formData, schemaEnum]);

  useEffect(() => {
    if (existingType && formData && !allowedTypes.includes(formData)) {
      onChange(existingType);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingType, allowedTypes]);

  const locked = allowedTypes.length <= 1;

  let helperText = uiSchema['ui:help'] ?? schema.description;
  if (existingType) {
    helperText = locked
      ? `This record's type (${existingType}) can't be changed without recreating it in Route53, which isn't allowed here. Delete and recreate the record instead if a different type is needed.`
      : 'A and ALIAS both map to Route53 record type A, so switching between them is safe and does not recreate the record.';
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
        <TextField
          id={idSchema?.$id}
          select
          label={schema.title ?? 'Record Type'}
          margin="dense"
          variant="outlined"
          required={required}
          fullWidth
          value={formData ?? ''}
          disabled={disabled || loading || locked}
          onChange={event => onChange(event.target.value)}
        >
          {allowedTypes.map(type => (
            <MenuItem key={type} value={type}>
              {type}
            </MenuItem>
          ))}
        </TextField>
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
