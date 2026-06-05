import { Entity } from '@backstage/catalog-model';
import { useEntityByRef } from './useEntityByRef';

export type Environment = 'dev' | 'hml' | 'prd';

const ALLOWED_ENVIRONMENTS = ['dev', 'hml', 'prd'] as const;

export type EnvironmentName = (typeof ALLOWED_ENVIRONMENTS)[number];

type SystemEnvironmentSpec = {
  name?: unknown;
  aws?: {
    account?: unknown;
    accountName?: unknown;
    region?: unknown;
  };
};

export type SystemEnvironment = {
  name: EnvironmentName;
  aws?: {
    account?: string;
    accountName?: string;
    region?: string;
  };
};

export type SystemAwsAccount = {
  accountId: string;
  accountName?: string;
  value: string;
};

export type SystemAwsConfig = SystemAwsAccount & {
  region?: string;
};

export function isEnvironment(value: unknown): value is Environment {
  return typeof value === 'string' && ALLOWED_ENVIRONMENTS.includes(value as EnvironmentName);
}

function toOptionalString(value: unknown): string | undefined {
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number') {
    return String(value);
  }
  return undefined;
}

function extractSystemEnvironments(entity?: Entity): SystemEnvironment[] {
  const rawEnvironments = entity?.spec?.environments;

  if (!Array.isArray(rawEnvironments)) {
    return [];
  }

  const unique = new Map<EnvironmentName, SystemEnvironment>();
  for (const item of rawEnvironments) {
    const candidate = typeof item === 'object' && item !== null ? (item as SystemEnvironmentSpec) : undefined;
    const name = candidate?.name;
    const normalized = typeof name === 'string' ? name.toLowerCase() : undefined;
    if (isEnvironment(normalized)) {
      unique.set(normalized, {
        name: normalized,
        aws: {
          account: toOptionalString(candidate?.aws?.account),
          accountName: toOptionalString(candidate?.aws?.accountName),
          region: toOptionalString(candidate?.aws?.region),
        },
      });
    }
  }

  return Array.from(unique.values());
}

export const useSystemEnvironments = ({ systemRef }: { systemRef?: string }) => {
  const { entity: systemEntity, loading, error } = useEntityByRef({ entityRef: systemRef });

  const system = systemEntity;
  const systemEnvironments = extractSystemEnvironments(system);
  const environments = systemEnvironments.map((environment) => environment.name);

  const getAwsFromEnvironment = (environmentName: EnvironmentName): SystemAwsConfig | undefined => {
    const match = systemEnvironments.find((environment) => environment.name === environmentName);
    const accountId = match?.aws?.account;

    if (!accountId) {
      return undefined;
    }

    const accountName = match?.aws?.accountName;
    const region = match?.aws?.region;

    return {
      accountId,
      accountName,
      region,
      value: accountName ? `${accountId}:${accountName}` : accountId,
    };
  };

  const getAwsAccountFromEnvironment = (environmentName: EnvironmentName): SystemAwsAccount | undefined => {
    const awsConfig = getAwsFromEnvironment(environmentName);
    if (!awsConfig) {
      return undefined;
    }

    return {
      accountId: awsConfig.accountId,
      accountName: awsConfig.accountName,
      value: awsConfig.value,
    };
  };

  return {
    system,
    systemEnvironments,
    environments,
    getAwsFromEnvironment,
    getAwsAccountFromEnvironment,
    loading,
    error,
    systemEntity,
  };
};
