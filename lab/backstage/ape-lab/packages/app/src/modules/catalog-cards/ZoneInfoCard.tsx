import React from 'react';
import {
  Chip,
  Link,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
  makeStyles,
} from '@material-ui/core';
import { InfoCard } from '@backstage/core-components';
import { useEntity } from '@backstage/plugin-catalog-react';

const useStyles = makeStyles(theme => ({
  cell: {
    fontFamily:
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 13,
    wordBreak: 'break-all',
  },
  label: {
    width: 160,
    color: theme.palette.text.secondary,
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  ns: {
    margin: theme.spacing(0.25),
  },
  empty: {
    color: theme.palette.text.disabled,
    fontStyle: 'italic',
    fontSize: 13,
  },
}));

export const ZoneInfoCard = () => {
  const classes = useStyles();
  const { entity } = useEntity();
  const a = entity.metadata.annotations ?? {};
  const zoneName = a['dock.tech/zone-name'];
  const zoneId = a['dock.tech/zone-id'];
  const visibility = a['dock.tech/visibility'];
  const parent = a['dock.tech/parent-zone-name'];
  const parentId = a['dock.tech/parent-zone-id'];
  const accountId = a['dock.tech/aws-account-id'];
  const accountName = a['dock.tech/aws-account-name'];
  const system = a['dock.tech/system'];
  const env = a['dock.tech/environment'];
  const ready = a['dock.tech/zone-ready'];
  const nameservers = (a['dock.tech/zone-nameservers'] || '')
    .split(',')
    .filter(Boolean);

  const rows: Array<[string, React.ReactNode]> = [
    ['Zone name', zoneName ?? <span className={classes.empty}>—</span>],
    [
      'Zone ID',
      zoneId ? (
        <Link
          href={`https://console.aws.amazon.com/route53/v2/hostedzones#ListRecordSets/${zoneId}`}
          target="_blank"
          rel="noreferrer"
        >
          {zoneId}
        </Link>
      ) : (
        <span className={classes.empty}>provisioning…</span>
      ),
    ],
    [
      'Status',
      <Chip
        size="small"
        label={ready === 'true' ? 'Ready' : ready === 'false' ? 'Not ready' : 'Unknown'}
        color={ready === 'true' ? 'primary' : 'default'}
      />,
    ],
    [
      'Visibility',
      visibility ? <Chip size="small" label={visibility} /> : '—',
    ],
    [
      'Delegated from',
      parent ? (
        <span>
          {parent}
          {parentId && (
            <Typography variant="caption" component="span" style={{ marginLeft: 8 }}>
              ({parentId})
            </Typography>
          )}
        </span>
      ) : (
        <span className={classes.empty}>apex zone (none)</span>
      ),
    ],
    [
      'AWS account',
      accountName || accountId ? `${accountName ?? ''} ${accountId ? `(${accountId})` : ''}`.trim() : '—',
    ],
    ['System', system ?? '—'],
    ['Environment', env ? <Chip size="small" label={env} /> : '—'],
    [
      'Nameservers',
      nameservers.length ? (
        <span>
          {nameservers.map(ns => (
            <Chip key={ns} className={classes.ns} size="small" label={ns} />
          ))}
        </span>
      ) : (
        <span className={classes.empty}>—</span>
      ),
    ],
  ];

  return (
    <InfoCard title="Zone">
      <Table size="small">
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label}>
              <TableCell className={classes.label}>{label}</TableCell>
              <TableCell className={classes.cell}>{value}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </InfoCard>
  );
};
