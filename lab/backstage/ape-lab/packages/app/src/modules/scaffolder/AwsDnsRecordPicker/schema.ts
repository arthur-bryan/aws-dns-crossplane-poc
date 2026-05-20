import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AwsDnsRecordPickerFieldSchema = makeFieldSchema({
  output: (z) =>
    z
      .object({
        name: z.string(),
        type: z.string(),
        ttl: z.number().optional(),
        values: z.array(z.string()),
        aliasTarget: z
          .object({
            dnsName: z.string(),
            hostedZoneId: z.string(),
            evaluateTargetHealth: z.boolean(),
          })
          .optional(),
        setIdentifier: z.string().optional(),
        weight: z.number().optional(),
      })
      .describe('The selected Route53 record'),
  uiOptions: (z) =>
    z
      .object({
        environment: z.enum(['dev', 'hml', 'prd']).optional().describe('Static environment used to fetch DNS records'),
        environmentFieldName: z.string().optional().describe('Form field name that holds the environment value'),
        zoneId: z.string().optional().describe('Static Route53 hosted zone ID used to fetch records'),
        zoneFieldName: z.string().optional().describe('Form field name that holds the zone ID value'),
      })
      .optional(),
});

export type AwsDnsRecordPickerUiOptions = NonNullable<(typeof AwsDnsRecordPickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type AwsDnsRecordPickerProps = typeof AwsDnsRecordPickerFieldSchema.TProps;

export const AwsDnsRecordPickerSchema = AwsDnsRecordPickerFieldSchema.schema;
