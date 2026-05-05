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

const stripZonePrefix = (name: string) =>
  name.startsWith('zone-') ? name.slice('zone-'.length) : name;

const parseRefName = (ref: string): string => {
  const last = ref.includes('/') ? ref.split('/').pop()! : ref;
  return last.includes(':') ? last.split(':').pop()! : last;
};

export const RecordFqdnPreview = (
  props: FieldExtensionComponentProps<string>,
) => {
  const classes = useStyles();
  const ctx = (props.formContext ?? {}) as { formData?: Record<string, any> };
  const data = ctx.formData ?? {};

  let zoneName = '';
  if (typeof data.zone === 'string' && data.zone) {
    zoneName = stripZonePrefix(parseRefName(data.zone));
  }

  const recordName = String(data.recordName ?? '').trim().toLowerCase();
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
