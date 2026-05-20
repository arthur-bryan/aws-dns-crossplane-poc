import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AwsDnsZonePickerFieldSchema = makeFieldSchema({
  output: (z) => z.string().describe('The selected Route53 hosted zone ID'),
  uiOptions: (z) =>
    z
      .object({
        environment: z.enum(['dev', 'hml', 'prd']).optional().describe('Static environment used to fetch DNS zones'),
        environmentFieldName: z.string().optional().describe('Form field name that holds the environment value'),
      })
      .optional(),
});

export type AwsDnsZonePickerUiOptions = NonNullable<(typeof AwsDnsZonePickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type AwsDnsZonePickerProps = typeof AwsDnsZonePickerFieldSchema.TProps;

export const AwsDnsZonePickerSchema = AwsDnsZonePickerFieldSchema.schema;
