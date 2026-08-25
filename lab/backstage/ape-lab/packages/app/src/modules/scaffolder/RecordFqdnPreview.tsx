import { parseEntityRef } from '@backstage/catalog-model';
import Typography from '@material-ui/core/Typography';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

function getParentFormDataFromId(formData: unknown, id?: string): Record<string, unknown> | undefined {
  if (!id || !formData || typeof formData !== 'object') return undefined;
  const withoutRoot = id.replace(/^root_?/, '');
  if (!withoutRoot) return formData as Record<string, unknown>;
  const segments = withoutRoot.split('_');
  if (segments.length <= 1) return formData as Record<string, unknown>;
  let current: unknown = formData;
  for (const segment of segments.slice(0, -1)) {
    if (!current || typeof current !== 'object') return undefined;
    current = Array.isArray(current) ? current[Number(segment)] : (current as Record<string, unknown>)[segment];
  }
  return current as Record<string, unknown>;
}

function extractContext(composedName: string, systemName: string, environment: string): string {
  const prefix = systemName ? `${systemName}-` : '';
  const suffix = `-${environment}`;
  let ctx = composedName;
  if (prefix && ctx.startsWith(prefix)) ctx = ctx.slice(prefix.length);
  if (suffix && ctx.endsWith(suffix)) ctx = ctx.slice(0, ctx.length - suffix.length);
  return ctx;
}

export const RecordFqdnPreview = (props: FieldExtensionComponentProps<string>) => {
  const { formContext, idSchema } = props;
  const formData = ((formContext ?? {}) as { formData?: Record<string, any> }).formData;

  const arrayItem = getParentFormDataFromId(formData, idSchema?.$id);
  const composedName = arrayItem?.['name'];
  const zone = (formData as any)?.zone;
  const rawSystem = (formData as any)?.system;
  const rawEnvironment = (formData as any)?.environment;

  const zoneName = typeof (zone as any)?.name === 'string' ? (zone as any).name.trim() : '';
  const environment = typeof rawEnvironment === 'string' ? rawEnvironment.trim() : '';

  let systemName = '';
  if (typeof rawSystem === 'string') {
    try {
      systemName = parseEntityRef(rawSystem, { defaultKind: 'system' }).name;
    } catch {
      systemName = '';
    }
  }

  if (typeof composedName !== 'string' || !composedName || !zoneName || !environment) return null;

  const context = extractContext(composedName.trim(), systemName, environment);
  if (!context) return null;

  const fqdn = `${context}.${zoneName}`;

  return (
    <Typography variant="body2" style={{ marginTop: 4, color: '#666' }}>
      {fqdn}
    </Typography>
  );
};
