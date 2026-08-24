import { parseEntityRef } from '@backstage/catalog-model';
import Typography from '@material-ui/core/Typography';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

function getObjectPathValue(source: unknown, path: string): unknown {
  if (!path) return undefined;
  return path.split('.').reduce<unknown>((acc, segment) => {
    if (!acc || typeof acc !== 'object') return undefined;
    return (acc as Record<string, unknown>)[segment];
  }, source);
}

function findNestedValueByKey(source: unknown, key: string): unknown {
  if (!source || typeof source !== 'object') return undefined;
  const visited = new Set<object>();
  const queue: unknown[] = [source];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || typeof current !== 'object') continue;
    if (visited.has(current as object)) continue;
    visited.add(current as object);
    const record = current as Record<string, unknown>;
    if (record[key] !== undefined) return record[key];
    for (const v of Object.values(record)) {
      if (v && typeof v === 'object') queue.push(v);
    }
  }
  return undefined;
}

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

function resolveDependentFieldValue(formData: unknown, id: string | undefined, fieldName: string): unknown {
  const direct = getObjectPathValue(formData, fieldName);
  if (direct !== undefined) return direct;
  const nestedFromRoot = findNestedValueByKey(formData, fieldName);
  if (nestedFromRoot !== undefined) return nestedFromRoot;
  const parentFormData = getParentFormDataFromId(formData, id);
  if (!parentFormData) return undefined;
  const parentDirect = parentFormData[fieldName];
  if (parentDirect !== undefined) return parentDirect;
  return getObjectPathValue(parentFormData, fieldName);
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

  const composedName = resolveDependentFieldValue(formData, idSchema?.$id, 'name');
  const zone = resolveDependentFieldValue(formData, idSchema?.$id, 'zone');
  const rawSystem = resolveDependentFieldValue(formData, idSchema?.$id, 'system');
  const rawEnvironment = resolveDependentFieldValue(formData, idSchema?.$id, 'environment');

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
