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

function systemNameFromRef(systemRef: string): string {
  const ref = systemRef.includes('/') ? systemRef.split('/').pop()! : systemRef;
  return ref.includes(':') ? ref.split(':').pop()! : ref;
}

export function computeZoneFqdn(system: string, environment: string, isPrivate: boolean, rootDomain: string): string {
  const systemName = systemNameFromRef(system.trim());
  if (!systemName || !environment || !rootDomain) return '';
  const visibilityPart = isPrivate ? '.internal' : '';
  const environmentPart = environment === 'prd' ? '' : `.${environment}`;
  return `${systemName}${visibilityPart}${environmentPart}.${rootDomain}`;
}

export const ZoneFqdnPreview = (props: FieldExtensionComponentProps<string>) => {
  const classes = useStyles();
  const ctx = (props.formContext ?? {}) as { formData?: Record<string, any> };
  const data = ctx.formData ?? {};
  const uiOptions = ((props.uiSchema ?? {}) as Record<string, any>)['ui:options'] ?? {};
  const rootDomain = String(uiOptions.rootDomain ?? '').replace(/^\.+|\.+$/g, '');

  const fqdn = computeZoneFqdn(
    String(data.system ?? ''),
    String(data.environment ?? '').trim(),
    data.private === true,
    rootDomain,
  );

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
