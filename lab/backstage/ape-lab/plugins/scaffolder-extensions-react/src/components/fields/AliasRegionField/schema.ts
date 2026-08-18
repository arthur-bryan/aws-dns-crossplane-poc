import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AliasRegionFieldFieldSchema = makeFieldSchema({
  output: (z) => z.string().optional().describe('AWS region for the alias target, self-correcting on serviceType change'),
  uiOptions: (z) => z.object({}).optional(),
});

export type AliasRegionFieldProps = typeof AliasRegionFieldFieldSchema.TProps;

export const AliasRegionFieldSchema = AliasRegionFieldFieldSchema.schema;
