import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const WeightedSetIdentifierFieldFieldSchema = makeFieldSchema({
  output: (z) => z.string().optional().describe('Weighted routing SetIdentifier, cleared when weighted routing is disabled'),
  uiOptions: (z) => z.object({}).optional(),
});

export type WeightedSetIdentifierFieldProps = typeof WeightedSetIdentifierFieldFieldSchema.TProps;

export const WeightedSetIdentifierFieldSchema = WeightedSetIdentifierFieldFieldSchema.schema;
