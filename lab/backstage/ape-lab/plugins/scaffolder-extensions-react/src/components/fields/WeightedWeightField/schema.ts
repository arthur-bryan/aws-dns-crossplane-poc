import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const WeightedWeightFieldFieldSchema = makeFieldSchema({
  output: (z) => z.number().optional().describe('Weighted routing weight (0-255), cleared when weighted routing is disabled'),
  uiOptions: (z) => z.object({}).optional(),
});

export type WeightedWeightFieldProps = typeof WeightedWeightFieldFieldSchema.TProps;

export const WeightedWeightFieldSchema = WeightedWeightFieldFieldSchema.schema;
