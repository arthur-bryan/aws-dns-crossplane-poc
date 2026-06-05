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
    fontFamily:
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 14,
    color: theme.palette.text.primary,
    wordBreak: 'break-all',
  },
  empty: {
    fontFamily:
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 14,
    color: theme.palette.text.disabled,
  },
  apex: {
    fontSize: 12,
    color: theme.palette.text.secondary,
    marginLeft: theme.spacing(1),
  },
}));

function extractContext(composedName: string, system: string, environment: string): string {
  const ref = system.includes('/') ? system.split('/').pop()! : system;
  const systemName = ref.includes(':') ? ref.split(':').pop()! : ref;
  const prefix = systemName ? `${systemName}-` : '';
  const suffix = environment ? `-${environment}` : '';
  let context = composedName;
  if (prefix && context.startsWith(prefix)) {
    context = context.slice(prefix.length);
  }
  if (suffix && context.endsWith(suffix)) {
    context = context.slice(0, context.length - suffix.length);
  }
  return context;
}

export const RecordFqdnPreview = (
  props: FieldExtensionComponentProps<string>,
) => {
  const classes = useStyles();
  const ctx = (props.formContext ?? {}) as { formData?: Record<string, any> };
  const data = ctx.formData ?? {};

  const zone = data.zone;
  const zoneName = zone && typeof zone === 'object' ? String(zone.name ?? '').replace(/\.$/, '') : '';

  const composedName = String(data.name ?? '').trim();
  const system = String(data.system ?? '').trim();
  const environment = String(data.environment ?? '').trim();
  const recordName = composedName ? extractContext(composedName, system, environment) : '';

  const fqdn = zoneName
    ? recordName
      ? `${recordName}.${zoneName}`
      : zoneName
    : '';
  const isApex = !!zoneName && !recordName;

  return (
    <div className={classes.wrap}>
      <div className={classes.label}>Resulting record</div>
      {fqdn ? (
        <div className={classes.value}>
          {fqdn}
          {isApex && <span className={classes.apex}>(apex)</span>}
        </div>
      ) : (
        <div className={classes.empty}>—</div>
      )}
    </div>
  );
};
