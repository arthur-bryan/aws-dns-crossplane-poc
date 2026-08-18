import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const RecordTtlPreviewFieldSchema = makeFieldSchema({
  output: (z) => z.number().optional().describe('Read-only TTL preview, derived from environment/type/weighted routing'),
  uiOptions: (z) => z.object({}).optional(),
});

export type RecordTtlPreviewProps = typeof RecordTtlPreviewFieldSchema.TProps;

export const RecordTtlPreviewSchema = RecordTtlPreviewFieldSchema.schema;
