import type { Entity } from '@backstage/catalog-model';
import type {
  CatalogProcessor,
  CatalogProcessorEmit,
  LocationSpec,
} from '@backstage/plugin-catalog-node';
import type { LoggerService } from '@backstage/backend-plugin-api';
import { CustomObjectsApi, KubeConfig } from '@kubernetes/client-node';

const ZONE_TYPE = 'dns-zone';
const RECORD_TYPE = 'dns-record';
const ZONE_NAME_ANNOTATION = 'dock.tech/zone-name';
const ZONE_ID_ANNOTATION = 'dock.tech/zone-id';
const NAMESERVERS_ANNOTATION = 'dock.tech/zone-nameservers';
const READY_ANNOTATION = 'dock.tech/zone-ready';
const SCAFFOLDER_PARAMS_ANNOTATION = 'dock.tech/scaffolder-parameters';
const EDIT_URL_ANNOTATION = 'backstage.io/edit-url';
const RECORD_EDIT_TEMPLATE = '/create/templates/default/dns-record-edit';
const CACHE_TTL_MS = 25_000;

type ZoneStatus = {
  zoneId?: string;
  nameServers?: string[];
  ready?: boolean;
};

export class DockZoneEnrichmentProcessor implements CatalogProcessor {
  private cache = new Map<string, ZoneStatus>();
  private cacheLoadedAt = 0;
  private readonly k8s: CustomObjectsApi | undefined;
  private readonly logger: LoggerService;
  private warnedNoCluster = false;

  constructor(opts: { logger: LoggerService }) {
    this.logger = opts.logger.child({ processor: this.getProcessorName() });
    try {
      const kc = new KubeConfig();
      kc.loadFromDefault();
      this.k8s = kc.makeApiClient(CustomObjectsApi);
    } catch (err) {
      this.logger.warn(
        `kubeconfig discovery failed; zoneId enrichment disabled: ${err}`,
      );
      this.k8s = undefined;
    }
  }

  getProcessorName(): string {
    return 'DockZoneEnrichmentProcessor';
  }

  async preProcessEntity(
    entity: Entity,
    _location: LocationSpec,
    _emit: CatalogProcessorEmit,
  ): Promise<Entity> {
    if (entity.kind !== 'Resource') return entity;
    const specType = (entity.spec as { type?: unknown } | undefined)?.type;
    const annotations = entity.metadata.annotations ?? {};

    if (specType === ZONE_TYPE) {
      const zoneName = annotations[ZONE_NAME_ANNOTATION];
      if (!zoneName) return entity;
      const status = await this.lookup(zoneName);
      if (!status) return entity;

      const next: Record<string, string> = { ...annotations };
      if (status.zoneId) next[ZONE_ID_ANNOTATION] = status.zoneId;
      if (status.nameServers?.length) {
        next[NAMESERVERS_ANNOTATION] = status.nameServers.join(',');
      }
      if (status.ready !== undefined) {
        next[READY_ANNOTATION] = String(status.ready);
      }
      return { ...entity, metadata: { ...entity.metadata, annotations: next } };
    }

    if (specType === RECORD_TYPE) {
      // Derive the formData snapshot the edit template will pre-fill
      // from. Prefer the persisted scaffolder-parameters annotation
      // (written by record.yaml / record-edit.yaml / record-claim.yaml),
      // but fall back to synthesising a minimal snapshot from spec so
      // legacy records that never carried the annotation still get an
      // active Edit pencil in the UI. Also inject entityRef so the
      // RecordTypeField widget can look up the live catalog entity's
      // recordType.
      const entityRef = `resource:${entity.metadata.namespace ?? 'default'}/${entity.metadata.name}`;
      const params = synthesizeScaffolderParameters(entity, annotations, entityRef);
      if (!params) return entity;
      const fullEditUrl = `${RECORD_EDIT_TEMPLATE}?formData=${encodeURIComponent(params)}`;
      if (
        annotations[EDIT_URL_ANNOTATION] === fullEditUrl &&
        annotations[SCAFFOLDER_PARAMS_ANNOTATION] === params
      ) {
        return entity;
      }
      return {
        ...entity,
        metadata: {
          ...entity.metadata,
          annotations: {
            ...annotations,
            [SCAFFOLDER_PARAMS_ANNOTATION]: params,
            [EDIT_URL_ANNOTATION]: fullEditUrl,
          },
        },
      };
    }

    return entity;
  }

  private async lookup(zoneName: string): Promise<ZoneStatus | undefined> {
    await this.refreshIfStale();
    return this.cache.get(zoneName);
  }

  private async refreshIfStale(): Promise<void> {
    if (!this.k8s) return;
    const now = Date.now();
    if (now - this.cacheLoadedAt < CACHE_TTL_MS) return;

    try {
      const resp = await this.k8s.listClusterCustomObject({
        group: 'dock.tech',
        version: 'v1',
        plural: 'dnszones',
      });
      const items = this.extractItems(resp);
      const next = new Map<string, ZoneStatus>();
      for (const item of items) {
        const zoneName = item?.spec?.zoneName as string | undefined;
        if (!zoneName) continue;
        next.set(zoneName, {
          zoneId: item?.status?.zoneId,
          nameServers: item?.status?.nameServers,
          ready: item?.status?.ready,
        });
      }
      this.cache = next;
      this.cacheLoadedAt = now;
      this.warnedNoCluster = false;
      this.logger.debug(`refreshed zoneId cache (${next.size} zones)`);
    } catch (err) {
      if (!this.warnedNoCluster) {
        this.logger.warn(
          `failed to list zones.dock.tech; serving stale or empty cache: ${err}`,
        );
        this.warnedNoCluster = true;
      }
      this.cacheLoadedAt = now;
    }
  }

  private extractItems(resp: unknown): any[] {
    if (!resp) return [];
    const r = resp as { items?: unknown; body?: { items?: unknown } };
    if (Array.isArray(r.items)) return r.items as any[];
    if (Array.isArray(r.body?.items)) return r.body!.items as any[];
    return [];
  }
}

/**
 * Produce the scaffolder-parameters JSON string that will pre-fill the
 * edit form. Returns undefined if we can't produce anything useful.
 *
 * Precedence:
 *   1. Existing dock.tech/scaffolder-parameters annotation (parsed).
 *   2. Synthesised from spec fields as a fallback for legacy records
 *      that were imported/created before the create template started
 *      persisting the snapshot.
 *
 * Always ensures entityRef is present so the frontend
 * RecordTypeField widget can look up the live entity.
 */
function synthesizeScaffolderParameters(
  entity: Entity,
  annotations: Record<string, string>,
  entityRef: string,
): string | undefined {
  const persisted = annotations['dock.tech/scaffolder-parameters'];
  let params: Record<string, unknown> | undefined;
  if (persisted) {
    try {
      const parsed = JSON.parse(persisted);
      if (parsed && typeof parsed === 'object') {
        params = parsed as Record<string, unknown>;
      }
    } catch {
      // fall through to synthesis
    }
  }

  if (!params) {
    const spec = (entity.spec ?? {}) as Record<string, unknown>;
    const type = (spec.recordType ?? spec.type) as string | undefined;
    if (!type) return undefined;
    const alias = spec.aliasTarget as Record<string, unknown> | undefined;
    params = {
      name: entity.metadata.name,
      system:
        typeof spec.system === 'string'
          ? spec.system
          : `system:${entity.metadata.namespace ?? 'default'}/dns`,
      environment: spec.environment,
      zone: spec.zoneName,
      zoneId: spec.zoneId,
      recordName: spec.recordName ?? '',
      type,
      originalType: type,
      enableWeightedRouting: spec.setIdentifier ? true : false,
    };
    if (alias) {
      params.serviceType = alias.serviceType ?? 'Custom';
      params.dnsName = alias.dnsName;
      params.customZoneId = alias.hostedZoneId;
      params.evaluateTargetHealth = alias.evaluateTargetHealth ?? false;
    } else if (Array.isArray(spec.values)) {
      params.values = spec.values;
    }
    if (spec.setIdentifier) params.setIdentifier = spec.setIdentifier;
    if (spec.weight !== undefined) params.weight = spec.weight;
  }

  // entityRef is derived, not user-supplied -- overwrite whatever is
  // there (including undefined) so the widget can always find it.
  params.entityRef = entityRef;

  return JSON.stringify(params);
}
