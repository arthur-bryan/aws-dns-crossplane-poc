import Typography from '@material-ui/core/Typography';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';
import { getParentFormDataFromId } from '../utils';

// Mirrors the backend's `extractRecordName` jsonata step (record.yaml) so the
// live preview matches the record name that actually gets created: strips the
// `<system>-` prefix and `-<environment>` suffix off the composed entity name.
function extractRecordName(composedName: string, systemRef: string, environment: string): string {
  const ref = systemRef.includes('/') ? systemRef.split('/').pop()! : systemRef;
  const systemName = ref.includes(':') ? ref.split(':').pop()! : ref;
  const prefix = systemName ? `${systemName}-` : '';
  const suffix = environment ? `-${environment}` : '';
  let name = composedName;
  if (prefix && name.startsWith(prefix)) {
    name = name.slice(prefix.length);
  }
  if (suffix && name.endsWith(suffix)) {
    name = name.slice(0, name.length - suffix.length);
  }
  return name;
}

export const RecordFqdnPreview = (props: FieldExtensionComponentProps<string>) => {
  const data = ((props.formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};

  // When nested inside the `records` array (multi-record template), RJSF's
  // idSchema.$id looks like `root_records_2_fqdnPreview` -- resolve this
  // field's own array item so we read the sibling `name` from the correct
  // record instead of the form root. Falls back to root formData itself for
  // record-edit.yaml's flat single-record schema (id has no `records` segment).
  const record = (getParentFormDataFromId(data, props.idSchema?.$id) ?? data) as Record<string, any>;

  const composedName = typeof record.name === 'string' ? record.name.trim() : '';
  const zoneName = typeof data.zone?.name === 'string' ? data.zone.name.trim() : '';
  const system = typeof data.system === 'string' ? data.system.trim() : '';
  const environment = typeof data.environment === 'string' ? data.environment.trim() : '';

  const recordName = composedName ? extractRecordName(composedName, system, environment) : '';

  if (!recordName || !zoneName) return null;

  const fqdn = `${recordName}.${zoneName}`;

  return (
    <Typography variant="body2" style={{ marginTop: 4, color: '#666' }}>
      {fqdn}
    </Typography>
  );
};
