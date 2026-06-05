import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import { useEffect, useMemo } from 'react';
import { Environment, isEnvironment, useSystemEnvironments } from './hooks/useSystemEnvironments';
import { EnvironmentPickerProps } from './EnvironmentPickerSchema';

export const EnvironmentPicker = (props: EnvironmentPickerProps) => {
  const { onChange, formData, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;
  const uiOptions = uiSchema['ui:options'] ?? {};
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
      if (formData !== undefined) {
        onChange(undefined);
      }
      return;
    }

    if (!isEnvironment(formData) || !options.includes(formData)) {
      onChange(fallbackEnvironment);
    }
  }, [fallbackEnvironment, formData, onChange, options]);

  let helperText = 'Select a System first to load environments from spec.environments.';

  if (systemRef) {
    if (loading) {
      helperText = 'Loading environments from selected System...';
    } else if (error) {
      helperText = 'Could not load environments from System.';
    } else if (systemEnvironments.length > 0) {
      helperText = `Loaded ${systemEnvironments.length} environment(s) from System: ${systemEnvironments.join(', ')}.`;
    } else {
      helperText = 'System has no supported environments in spec.environments.';
    }
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
          label={schema.title ?? 'Environment'}
          margin="dense"
          variant="outlined"
          required={required}
          fullWidth
          value={selectedEnvironment}
          disabled={disabled || loading || !systemRef || options.length === 0}
          onChange={(event) => onChange(event.target.value as Environment)}
        >
          <MenuItem value="">Select an environment</MenuItem>
          {options.map((environment) => (
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
