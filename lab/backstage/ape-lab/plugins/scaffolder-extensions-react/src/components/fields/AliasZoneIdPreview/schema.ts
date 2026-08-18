import { makeFieldSchema } from '@backstage/plugin-scaffolder-react';

export const AliasZoneIdPreviewFieldSchema = makeFieldSchema({
  output: (z) => z.string().optional().describe('Read-only preview of the resolved Route53 alias hosted-zone-ID'),
  uiOptions: (z) => z.object({}).optional(),
});

export type AliasZoneIdPreviewProps = typeof AliasZoneIdPreviewFieldSchema.TProps;

export const AliasZoneIdPreviewSchema = AliasZoneIdPreviewFieldSchema.schema;
