import React from 'react';
import {
  Chip,
  Table,
  TableBody,
  TableCell,
  TableRow,
  makeStyles,
} from '@material-ui/core';
import { InfoCard } from '@backstage/core-components';
import { useEntity } from '@backstage/plugin-catalog-react';

const useStyles = makeStyles(theme => ({
  mono: {
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
  empty: {
    color: theme.palette.text.disabled,
    fontStyle: 'italic',
    fontSize: 13,
  },
  chip: { margin: theme.spacing(0.25) },
}));

type Params = {
  recordName?: string;
  type?: string;
  ttl?: number;
  values?: string[];
  routingPolicy?: string;
  setIdentifier?: string;
  weight?: number;
  failoverType?: string;
  healthCheckId?: string;
  latencyRegion?: string;
  geoContinent?: string;
  geoCountry?: string;
  geoSubdivision?: string;
  geoproxAwsRegion?: string;
  geoproxLatitude?: string;
  geoproxLongitude?: string;
  geoproxBias?: number;
  serviceType?: string;
  dnsName?: string;
  evaluateTargetHealth?: boolean;
  targetRegion?: string;
  customZoneId?: string;
};

const tryParse = (raw: string | undefined): Params | undefined => {
  if (!raw) return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
};

const formatValues = (p: Params): React.ReactNode => {
  if (p.type === 'ALIAS') {
    return (
      <span>
        {p.serviceType} → {p.dnsName}
        {p.targetRegion ? ` (${p.targetRegion})` : ''}
      </span>
    );
  }
  if (!p.values?.length) return '—';
  return p.values.map((v, i) => <div key={`${v}-${i}`}>{v}</div>);
};

const policyDetail = (p: Params): React.ReactNode => {
  switch (p.routingPolicy) {
    case 'weighted':
      return `weight=${p.weight ?? 0}`;
    case 'failover':
      return `${p.failoverType ?? '?'}${p.healthCheckId ? ` · hc=${p.healthCheckId}` : ''}`;
    case 'latency':
      return `region=${p.latencyRegion ?? '?'}`;
    case 'geolocation':
      return [p.geoContinent, p.geoCountry, p.geoSubdivision]
        .filter(Boolean)
        .join(' / ') || '—';
    case 'geoproximity':
      return p.geoproxAwsRegion
        ? `aws=${p.geoproxAwsRegion} bias=${p.geoproxBias ?? 0}`
        : `lat=${p.geoproxLatitude} lon=${p.geoproxLongitude} bias=${p.geoproxBias ?? 0}`;
    case 'multivalue':
      return p.healthCheckId ? `hc=${p.healthCheckId}` : 'multivalue';
    default:
      return '—';
  }
};

export const RecordInfoCard = () => {
  const classes = useStyles();
  const { entity } = useEntity();
  const a = entity.metadata.annotations ?? {};
  const params = tryParse(a['dock.tech/scaffolder-parameters']) ?? {};
  const fqdn = a['dock.tech/record-fqdn'] || '—';
  const type = a['dock.tech/record-type'] || params.type;
  const zoneName = a['dock.tech/zone-name'];
  const zoneId = a['dock.tech/zone-id'];
  const env = a['dock.tech/environment'];
  const policy = params.routingPolicy ?? 'simple';

  const rows: Array<[string, React.ReactNode]> = [
    ['FQDN', fqdn],
    ['Type', type ? <Chip size="small" label={type} /> : '—'],
    ['Values', formatValues(params)],
    ['TTL', params.ttl !== undefined ? `${params.ttl}s` : '—'],
    [
      'Routing policy',
      <span>
        <Chip size="small" label={policy} className={classes.chip} />
        {policy !== 'simple' && (
          <span className={classes.mono}>{policyDetail(params)}</span>
        )}
      </span>,
    ],
    [
      'Set ID',
      params.setIdentifier ? (
        <Chip size="small" label={params.setIdentifier} />
      ) : (
        <span className={classes.empty}>—</span>
      ),
    ],
    [
      'Zone',
      zoneName
        ? `${zoneName}${zoneId ? ` (${zoneId})` : ''}`
        : '—',
    ],
    ['Environment', env ? <Chip size="small" label={env} /> : '—'],
  ];

  return (
    <InfoCard title="Record">
      <Table size="small">
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label}>
              <TableCell className={classes.label}>{label}</TableCell>
              <TableCell className={classes.mono}>{value}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </InfoCard>
  );
};
