import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import TextField from '@material-ui/core/TextField';

// TTL is not user-editable -- it's fully derived from environment + record type
// + weighted-routing status (mirrors the backend's deriveTtl jsonata step
// verbatim, see record-edit.yaml). Shown read-only so the user can see what
// will actually be written without being able to set an inconsistent value.
export const RecordTtlPreview = (props: FieldExtensionComponentProps<number>) => {
  const { formContext, schema, uiSchema, idSchema, rawErrors, errors, required, disabled } = props;
  const data = ((formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};

  const type = data.type as string | undefined;

  // ALIAS records have no TTL of their own -- Route53 uses the alias target's.
  if (!type || type === 'ALIAS') {
    return null;
  }

  const environment = data.environment as string | undefined;
  const weighted = data.enableWeightedRouting === true;
  const isPrd = environment === 'prd';
  const isNs = type === 'NS';
  const ttl = weighted && !isPrd ? 600 : isNs ? 172800 : 3600;

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
        label={schema.title ?? 'TTL (seconds)'}
        value={ttl}
        disabled
        margin="dense"
        variant="outlined"
        fullWidth
        helperText={uiSchema['ui:help'] ?? schema.description}
      />
    </ScaffolderField>
  );
};
