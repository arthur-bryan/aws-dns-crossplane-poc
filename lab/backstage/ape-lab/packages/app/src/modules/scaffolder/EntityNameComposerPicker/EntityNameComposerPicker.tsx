import { parseEntityRef } from '@backstage/catalog-model';
import { ScaffolderField } from '@backstage/plugin-scaffolder-react/alpha';
import FormHelperText from '@material-ui/core/FormHelperText';
import TextField from '@material-ui/core/TextField';
import { useEffect, useMemo, useState } from 'react';

import { EntityNameComposerPickerProps } from './schema';
import { isEnvironment, useSystemEnvironments } from '../hooks/useSystemEnvironments';

function normalizePart(value: string, joinCharacter: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, joinCharacter)
    .replace(/[^a-z0-9-_.]/g, '')
    .replace(new RegExp(`${joinCharacter}{2,}`, 'g'), joinCharacter)
    .replace(/^[\-_.]+|[\-_.]+$/g, '');
}

function composeName(parts: Array<string | undefined>, joinCharacter: string): string {
  return parts.filter(Boolean).join(joinCharacter);
}

function inferContextFromComposedName({
  value,
  system,
  environment,
  suffix,
  joinCharacter,
}: {
  value?: string;
  system?: string;
  environment?: string;
  suffix?: string;
  joinCharacter: string;
}): string {
  if (!value || !environment) {
    return '';
  }

  const envSuffix = suffix ? `${joinCharacter}${environment}${joinCharacter}${suffix}` : `${joinCharacter}${environment}`;

  if (!value.endsWith(envSuffix)) {
    return '';
  }

  let withoutSuffix = value.slice(0, value.length - envSuffix.length);

  if (system) {
    const prefix = `${system}${joinCharacter}`;
    if (!withoutSuffix.startsWith(prefix)) {
      return '';
    }
    withoutSuffix = withoutSuffix.slice(prefix.length);
  }

  return withoutSuffix;
}

export const EntityNameComposerPicker = (props: EntityNameComposerPickerProps) => {
  const { onChange, formData, formContext, required, rawErrors, errors, schema, uiSchema, idSchema, disabled } = props;

  const uiOptions = uiSchema['ui:options'] ?? {};
  const joinCharacter = typeof uiOptions.joinCharacter === 'string' && uiOptions.joinCharacter.length > 0 ? uiOptions.joinCharacter : '-';
  const suffix = typeof uiOptions.suffix === 'string' ? normalizePart(uiOptions.suffix, joinCharacter) : undefined;
  const maxLength = typeof uiOptions.maxLength === 'number' ? uiOptions.maxLength : undefined;

  const environmentFieldName = uiOptions.environmentFieldName ?? 'environment';
  const rawEnvironment = uiOptions.environment ?? formContext?.formData?.[environmentFieldName];
  const environment = isEnvironment(rawEnvironment) ? rawEnvironment : undefined;

  const systemFieldName = uiOptions.systemFieldName ?? 'system';
  const systemFromForm = formContext?.formData?.[systemFieldName];
  const rawSystemRef = uiOptions.systemRef ?? systemFromForm;
  const systemRef = typeof rawSystemRef === 'string' ? rawSystemRef : undefined;

  const { system, loading, error } = useSystemEnvironments({ systemRef });

  const systemName = useMemo(() => {
    if (system?.metadata?.name) {
      return normalizePart(system.metadata.name, joinCharacter);
    }

    if (!systemRef) {
      return undefined;
    }

    try {
      return normalizePart(parseEntityRef(systemRef, { defaultKind: 'system' }).name, joinCharacter);
    } catch {
      return undefined;
    }
  }, [joinCharacter, system?.metadata?.name, systemRef]);

  const normalizedEnvironment = environment ? normalizePart(environment, joinCharacter) : undefined;

  const valueAsString = typeof formData === 'string' ? formData : undefined;

  const [contextValue, setContextValue] = useState<string>(() =>
    inferContextFromComposedName({
      value: valueAsString,
      system: systemName,
      environment: normalizedEnvironment,
      suffix,
      joinCharacter,
    }),
  );

  useEffect(() => {
    if (!valueAsString) {
      return;
    }

    const inferredContext = inferContextFromComposedName({
      value: valueAsString,
      system: systemName,
      environment: normalizedEnvironment,
      suffix,
      joinCharacter,
    });

    setContextValue((prev) => (prev === inferredContext ? prev : inferredContext));
  }, [joinCharacter, normalizedEnvironment, suffix, systemName, valueAsString]);

  const normalizedContext = normalizePart(contextValue, joinCharacter);
  const composedName = composeName([systemName, normalizedContext, normalizedEnvironment, suffix], joinCharacter);
  const exceedsMaxLength = Boolean(maxLength && composedName.length > maxLength);

  useEffect(() => {
    if (!normalizedEnvironment || !normalizedContext) {
      if (formData !== undefined) {
        onChange(undefined);
      }
      return;
    }

    if (maxLength && composedName.length > maxLength) {
      if (formData !== undefined) {
        onChange(undefined);
      }
      return;
    }

    if (formData !== composedName) {
      onChange(composedName);
    }
  }, [composedName, formData, maxLength, normalizedContext, normalizedEnvironment, onChange]);

  let helperText = 'Select environment and type context to compose the name.';

  if (systemRef && loading) {
    helperText = 'Loading system details...';
  } else if (systemRef && error) {
    helperText = 'Could not load system details.';
  } else if (!environment) {
    helperText = 'Select an environment first.';
  } else if (!contextValue) {
    helperText = `Name format: ${systemName ? `<system>${joinCharacter}` : ''}<context>${joinCharacter}<environment>${
      suffix ? `${joinCharacter}<suffix>` : ''
    }`;
  } else if (exceedsMaxLength && maxLength) {
    helperText = `Composed name exceeds maxLength (${composedName.length}/${maxLength}).`;
  } else {
    helperText = `Preview: ${composedName}`;
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
          label={schema.title ?? 'Entity Name Context'}
          margin="dense"
          variant="outlined"
          required={required}
          inputProps={{ maxLength }}
          fullWidth
          value={contextValue}
          disabled={disabled || (Boolean(systemRef) && loading) || !normalizedEnvironment}
          onChange={(event) => setContextValue(event.target.value)}
        />
        <FormHelperText>{helperText}</FormHelperText>
      </>
    </ScaffolderField>
  );
};
