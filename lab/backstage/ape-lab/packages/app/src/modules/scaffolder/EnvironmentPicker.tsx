import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import { useEffect, useMemo } from 'react';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { Environment, isEnvironment, useSystemEnvironments } from './hooks/useSystemEnvironments';

export const EnvironmentPicker = (
  props: FieldExtensionComponentProps<string>,
) => {
  const { onChange, formData, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } =
    props;
  const uiOptions = (uiSchema as any)['ui:options'] ?? {};
  const systemFieldName = uiOptions.systemFieldName ?? 'system';
  const systemFromForm = props.formContext?.formData?.[systemFieldName];
  const rawSystemRef = uiOptions.systemRef ?? systemFromForm;
  const systemRef = typeof rawSystemRef === 'string' ? rawSystemRef : undefined;

  const { environments: systemEnvironments, loading, error } = useSystemEnvironments({ systemRef });

  const options = useMemo(() => systemEnvironments, [systemEnvironments]);
  const fallbackEnvironment = options[0];
  const selectedEnvironment = formData ? formData : fallbackEnvironment ?? '';

  useEffect(() => {
    if (options.length === 0) {
      if (formData !== undefined) onChange(undefined);
      return;
    }
    if (!isEnvironment(formData) || !options.includes(formData as Environment)) {
      onChange(fallbackEnvironment);
    }
  }, [fallbackEnvironment, formData, onChange, options]);

  let helperText = 'Select a System first.';
  if (systemRef) {
    if (loading) {
      helperText = 'Loading environments…';
    } else if (error) {
      helperText = 'Could not load environments for this system.';
    } else if (systemEnvironments.length > 0) {
      helperText = `Available environments: ${systemEnvironments.join(', ')}.`;
    } else {
      helperText = 'This system has no environments configured.';
    }
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
        <TextField
          id={idSchema?.$id}
          select
          label={schema.title ?? 'Environment'}
          margin="dense"
          variant="outlined"
          required={required}
          fullWidth
          value={selectedEnvironment}
          disabled={disabled || loading || !systemRef || options.length === 0}
          onChange={event => onChange(event.target.value as Environment)}
        >
          <MenuItem value="">Select an environment</MenuItem>
          {options.map(environment => (
            <MenuItem key={environment} value={environment}>
              {environment}
            </MenuItem>
          ))}
        </TextField>
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
