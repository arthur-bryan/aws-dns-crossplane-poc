import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const EnvironmentPickerFieldSchema = makeFieldSchema({
  output: (z) => z.enum(['dev', 'hml', 'prd']).describe('Selected deployment environment'),
  uiOptions: (z) =>
    z
      .object({
        systemRef: z.string().optional().describe('Static System entity ref used to resolve environments from spec.environments'),
        systemFieldName: z.string().optional().describe('Form field name that holds the System entity ref'),
      })
      .optional(),
});

export type EnvironmentPickerUiOptions = NonNullable<(typeof EnvironmentPickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type EnvironmentPickerProps = typeof EnvironmentPickerFieldSchema.TProps;

export const EnvironmentPickerSchema = EnvironmentPickerFieldSchema.schema;
