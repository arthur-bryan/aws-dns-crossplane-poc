import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AwsVpcPickerFieldSchema = makeFieldSchema({
  output: (z) =>
    z
      .array(
        z.object({
          vpcId: z.string(),
          vpcRegion: z.string(),
        }),
      )
      .describe('The selected AWS VPCs'),
  uiOptions: (z) =>
    z
      .object({
        environment: z.enum(['dev', 'hml', 'prd']).optional().describe('Static environment used to fetch AWS VPCs'),
        environmentFieldName: z.string().optional().describe('Form field name that holds the environment value'),
        excludeDefault: z.boolean().optional().describe('Hide the account default VPC from the options'),
      })
      .optional(),
});

export type AwsVpcPickerUiOptions = NonNullable<(typeof AwsVpcPickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type AwsVpcPickerProps = typeof AwsVpcPickerFieldSchema.TProps;

export const AwsVpcPickerSchema = AwsVpcPickerFieldSchema.schema;
