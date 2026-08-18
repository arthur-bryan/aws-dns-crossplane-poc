import { Router } from 'express';
import {
  Route53Client,
  ListHostedZonesCommand,
  ListResourceRecordSetsCommand,
  HostedZone,
  ResourceRecordSet,
} from '@aws-sdk/client-route-53';
import { fromTemporaryCredentials } from '@aws-sdk/credential-providers';
import type { LoggerService, RootConfigService } from '@backstage/backend-plugin-api';

type DnsAccountConfig = {
  accountId: string;
  accountName: string;
  roleArn: string;
};

function getAccountConfig(
  config: RootConfigService,
  environment: string,
): DnsAccountConfig {
  const accountId = config.getString(
    `dns.accounts.${environment}.accountId`,
  );
  // accountName defaults to the environment key if not explicitly configured
  const accountName =
    config.getOptionalString(`dns.accounts.${environment}.accountName`) ?? environment;
  // roleArn is optional: when empty, the backend uses its default credential
  // chain (useful for the env whose account IS the backend's own account, so
  // no cross-account AssumeRole is needed).
  const roleArn =
    config.getOptionalString(`dns.accounts.${environment}.roleArn`) ?? '';
  return { accountId, accountName, roleArn };
}

function makeRoute53Client(roleArn: string): Route53Client {
  return new Route53Client({
    region: 'us-east-1',
    ...(roleArn
      ? {
          credentials: fromTemporaryCredentials({
            params: { RoleArn: roleArn },
          }),
        }
      : {}),
  });
}

async function listAllZones(client: Route53Client): Promise<HostedZone[]> {
  const zones: HostedZone[] = [];
  let marker: string | undefined;

  do {
    const resp = await client.send(
      new ListHostedZonesCommand({ Marker: marker, MaxItems: 100 }),
    );
    zones.push(...(resp.HostedZones ?? []));
    marker = resp.IsTruncated ? resp.NextMarker : undefined;
  } while (marker);

  return zones;
}

async function listAllRecords(
  client: Route53Client,
  zoneId: string,
): Promise<ResourceRecordSet[]> {
  const records: ResourceRecordSet[] = [];
  let nextName: string | undefined;
  let nextType: string | undefined;

  do {
    const resp = await client.send(
      new ListResourceRecordSetsCommand({
        HostedZoneId: zoneId,
        MaxItems: 300,
        StartRecordName: nextName,
        StartRecordType: nextType as any,
      }),
    );
    records.push(...(resp.ResourceRecordSets ?? []));
    if (resp.IsTruncated) {
      nextName = resp.NextRecordName;
      nextType = resp.NextRecordType;
    } else {
      nextName = undefined;
    }
  } while (nextName);

  return records;
}

export async function createDnsRouter(opts: {
  logger: LoggerService;
  config: RootConfigService;
}): Promise<Router> {
  const { logger, config } = opts;
  const router = Router();

  router.get('/dns-zones', async (req, res) => {
    const environment = req.query.environment as string | undefined;
    const environments = environment ? [environment] : ['dev', 'hml', 'prd'];

    try {
      const results = await Promise.all(
        environments.map(async env => {
          const { roleArn, accountName } = getAccountConfig(config, env);
          const client = makeRoute53Client(roleArn);
          const zones = await listAllZones(client);
          return zones.map(z => ({
            id: z.Id?.replace('/hostedzone/', ''),
            name: z.Name?.replace(/\.$/, ''),
            private: z.Config?.PrivateZone ?? false,
            recordCount: z.ResourceRecordSetCount,
            accountName,
            environment: env,
          }));
        }),
      );
      res.json({ zones: results.flat() });
    } catch (err: any) {
      logger.error(`Failed to list zones for ${environment ?? 'all'}: ${err.message}`);
      res.status(500).json({ error: err.message });
    }
  });

  router.get('/dns-records', async (req, res) => {
    const environment = req.query.environment as string;
    const zoneId = req.query.zoneId as string;

    if (!environment || !zoneId) {
      res
        .status(400)
        .json({ error: 'environment and zoneId query params required' });
      return;
    }

    try {
      const { roleArn } = getAccountConfig(config, environment);
      const client = makeRoute53Client(roleArn);
      const records = await listAllRecords(client, zoneId);

      // NS and SOA at the apex are zone-level system records managed by
      // Route53 itself -- they are not user-onboardable and must never appear
      // in the claim picker. Filter at the source so the API never surfaces
      // them to any consumer.
      const claimable = records.filter(
        r => r.Type !== 'NS' && r.Type !== 'SOA',
      );

      res.json({
        records: claimable.map(r => ({
          name: r.Name?.replace(/\.$/, ''),
          type: r.Type,
          ttl: r.TTL,
          values: r.ResourceRecords?.map(rr => rr.Value) ?? [],
          aliasTarget: r.AliasTarget
            ? {
                dnsName: r.AliasTarget.DNSName?.replace(/\.$/, ''),
                hostedZoneId: r.AliasTarget.HostedZoneId,
                evaluateTargetHealth:
                  r.AliasTarget.EvaluateTargetHealth ?? false,
              }
            : undefined,
          setIdentifier: r.SetIdentifier,
          weight: r.Weight,
        })),
      });
    } catch (err: any) {
      logger.error(
        `Failed to list records for zone ${zoneId} in ${environment}: ${err.message}`,
      );
      res.status(500).json({ error: err.message });
    }
  });

  return router;
}
