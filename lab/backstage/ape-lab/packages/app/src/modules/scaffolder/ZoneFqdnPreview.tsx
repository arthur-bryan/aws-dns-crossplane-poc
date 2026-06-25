import React from 'react';
import { makeStyles } from '@material-ui/core';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

const useStyles = makeStyles(theme => ({
  wrap: {
    marginTop: theme.spacing(1),
    marginBottom: theme.spacing(1),
    padding: theme.spacing(1.5, 2),
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: theme.shape.borderRadius,
    background: theme.palette.background.default,
    fontFamily: theme.typography.fontFamily,
  },
  label: {
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: theme.palette.text.secondary,
    marginBottom: theme.spacing(0.5),
  },
  value: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 14,
    color: theme.palette.text.primary,
    wordBreak: 'break-all',
  },
  empty: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 14,
    color: theme.palette.text.disabled,
  },
}));

function extractSubdomain(composedName: string, systemRef: string, environment: string): string {
  const ref = systemRef.includes('/') ? systemRef.split('/').pop()! : systemRef;
  const systemName = ref.includes(':') ? ref.split(':').pop()! : ref;
  const prefix = systemName ? `${systemName}-` : '';
  const suffix = environment ? `-${environment}-zone` : '-zone';
  let subdomain = composedName;
  if (prefix && subdomain.startsWith(prefix)) {
    subdomain = subdomain.slice(prefix.length);
  }
  if (suffix && subdomain.endsWith(suffix)) {
    subdomain = subdomain.slice(0, subdomain.length - suffix.length);
  }
  return subdomain;
}

export const ZoneFqdnPreview = (props: FieldExtensionComponentProps<string>) => {
  const classes = useStyles();
  const ctx = (props.formContext ?? {}) as { formData?: Record<string, any> };
  const data = ctx.formData ?? {};

  const parentZone = data.parentZone;
  const parentZoneName = parentZone && typeof parentZone === 'object'
    ? String(parentZone.name ?? '').replace(/\.$/, '')
    : '';

  const composedName = String(data.name ?? '').trim();
  const environment = String(data.environment ?? '').trim();
  const systemRef = String(data.system ?? 'dns').trim();
  const subdomain = composedName ? extractSubdomain(composedName, systemRef, environment) : '';

  const fqdn = parentZoneName && subdomain ? `${subdomain}.${parentZoneName}` : '';

  return (
    <div className={classes.wrap}>
      <div className={classes.label}>Resulting zone</div>
      {fqdn ? (
        <div className={classes.value}>{fqdn}</div>
      ) : (
        <div className={classes.empty}>—</div>
      )}
    </div>
  );
};
