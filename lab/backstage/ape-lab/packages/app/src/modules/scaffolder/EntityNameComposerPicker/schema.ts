import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const EntityNameComposerPickerFieldSchema = makeFieldSchema({
  output: (z) => z.string().describe('Composed entity name'),
  uiOptions: (z) =>
    z
      .object({
        systemRef: z.string().optional().describe('Static System entity ref used to compose the entity name'),
        systemFieldName: z.string().optional().describe('Form field name that holds the System entity ref'),
        environment: z.enum(['dev', 'hml', 'prd']).optional().describe('Static environment used to compose the entity name'),
        environmentFieldName: z.string().optional().describe('Form field name that holds the selected environment'),
        suffix: z.string().optional().describe('Suffix appended to the composed name'),
        maxLength: z.number().int().positive().optional().describe('Maximum allowed length for composed name'),
        joinCharacter: z.string().optional().describe('Separator used to join the composed name parts. Defaults to -'),
      })
      .optional(),
});

export type EntityNameComposerPickerUiOptions = NonNullable<(typeof EntityNameComposerPickerFieldSchema.TProps.uiSchema)['ui:options']>;

export type EntityNameComposerPickerProps = typeof EntityNameComposerPickerFieldSchema.TProps;

export const EntityNameComposerPickerSchema = EntityNameComposerPickerFieldSchema.schema;
