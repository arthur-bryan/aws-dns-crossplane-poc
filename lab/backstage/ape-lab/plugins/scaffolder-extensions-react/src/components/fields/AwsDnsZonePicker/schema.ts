import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AwsDnsZonePickerFieldSchema = makeFieldSchema({
  output: (z) =>
    z
      .object({
        id: z.string(),
        name: z.string(),
        accountName: z.string().optional(),
      })
      .describe('The selected Route53 hosted zone'),
  uiOptions: (z) =>
    z
      .object({
        environment: z.enum(['dev', 'hml', 'prd']).optional().describe('Static environment used to fetch DNS zones'),
        environmentFieldName: z.string().optional().describe('Form field name that holds the environment value'),
        excludeClaimed: z.boolean().optional().describe('Hide zones already claimed in the catalog'),
      })
      .optional(),
});

export type AwsDnsZonePickerUiOptions = NonNullable<(typeof AwsDnsZonePickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type AwsDnsZonePickerProps = typeof AwsDnsZonePickerFieldSchema.TProps;

export const AwsDnsZonePickerSchema = AwsDnsZonePickerFieldSchema.schema;
