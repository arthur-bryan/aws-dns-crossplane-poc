import type { Entity } from '@backstage/catalog-model';
import type {
  CatalogProcessor,
  CatalogProcessorEmit,
  LocationSpec,
} from '@backstage/plugin-catalog-node';
import type { LoggerService } from '@backstage/backend-plugin-api';
import { CustomObjectsApi, KubeConfig } from '@kubernetes/client-node';

const ZONE_TYPE = 'aws-dns-zone';
const RECORD_TYPE = 'aws-dns-record';
const ZONE_NAME_ANNOTATION = 'dock.tech/zone-name';
const ZONE_ID_ANNOTATION = 'dock.tech/zone-id';
const NAMESERVERS_ANNOTATION = 'dock.tech/zone-nameservers';
const READY_ANNOTATION = 'dock.tech/zone-ready';
const SCAFFOLDER_PARAMS_ANNOTATION = 'dock.tech/scaffolder-parameters';
const EDIT_URL_ANNOTATION = 'backstage.io/edit-url';
const RECORD_EDIT_TEMPLATE = '/create/templates/default/aws-dns-record-edit';
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
      const params = annotations[SCAFFOLDER_PARAMS_ANNOTATION];
      if (!params) return entity;
      const fullEditUrl = `${RECORD_EDIT_TEMPLATE}?formData=${encodeURIComponent(params)}`;
      if (annotations[EDIT_URL_ANNOTATION] === fullEditUrl) return entity;
      return {
        ...entity,
        metadata: {
          ...entity.metadata,
          annotations: { ...annotations, [EDIT_URL_ANNOTATION]: fullEditUrl },
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
        plural: 'zones',
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
