import Typography from '@material-ui/core/Typography';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

function systemNameFromRef(systemRef: string): string {
  const ref = systemRef.includes('/') ? systemRef.split('/').pop()! : systemRef;
  return ref.includes(':') ? ref.split(':').pop()! : ref;
}

export const ZoneFqdnPreview = (props: FieldExtensionComponentProps<string>) => {
  const data = ((props.formContext ?? {}) as { formData?: Record<string, any> }).formData ?? {};
  const uiOptions = ((props.uiSchema ?? {}) as Record<string, any>)['ui:options'] ?? {};
  const rootDomain = String(uiOptions.rootDomain ?? '').replace(/^\.+|\.+$/g, '');

  const systemName = systemNameFromRef(typeof data.system === 'string' ? data.system.trim() : '');
  const environment = typeof data.environment === 'string' ? data.environment.trim() : '';

  if (!systemName || !environment || !rootDomain) return null;

  const visibilityPart = data.private === true ? '.internal' : '';
  const environmentPart = environment === 'prd' ? '' : `.${environment}`;
  const fqdn = `${systemName}${visibilityPart}${environmentPart}.${rootDomain}`;

  return (
    <Typography variant="body2" style={{ marginTop: 4, color: '#666' }}>
      {fqdn}
    </Typography>
  );
};
