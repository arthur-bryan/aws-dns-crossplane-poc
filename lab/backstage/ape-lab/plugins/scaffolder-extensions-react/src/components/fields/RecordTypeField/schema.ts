import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const RecordTypeFieldFieldSchema = makeFieldSchema({
  output: (z) => z.string().describe('Record type, constrained to Route53-safe transitions from the existing type'),
  uiOptions: (z) => z.object({}).optional(),
});

export type RecordTypeFieldProps = typeof RecordTypeFieldFieldSchema.TProps;

export const RecordTypeFieldSchema = RecordTypeFieldFieldSchema.schema;
