import { LoggerService } from '@backstage/backend-plugin-api';
import {
  EntityProvider,
  EntityProviderConnection,
  DeferredEntity,
} from '@backstage/plugin-catalog-node';
import * as chokidar from 'chokidar';
import * as fs from 'fs/promises';
import * as path from 'path';
import { glob } from 'glob';
import * as yaml from 'js-yaml';

type Options = {
  watchGlobs: string[];
  logger: LoggerService;
};

export class CatalogFileWatcherEntityProvider implements EntityProvider {
  private readonly watchGlobs: string[];
  private readonly logger: LoggerService;
  private connection?: EntityProviderConnection;
  private watcher?: chokidar.FSWatcher;
  private rescanTimer?: NodeJS.Timeout;

  constructor(options: Options) {
    this.watchGlobs = options.watchGlobs;
    this.logger = options.logger.child({
      target: 'CatalogFileWatcherEntityProvider',
    });
  }

  getProviderName(): string {
    return 'catalog-file-watcher';
  }

  async connect(connection: EntityProviderConnection): Promise<void> {
    this.connection = connection;
    await this.refresh();

    this.watcher = chokidar.watch(this.watchGlobs, {
      ignoreInitial: true,
      awaitWriteFinish: { stabilityThreshold: 500, pollInterval: 100 },
    });

    const trigger = (event: string, file: string) => {
      this.logger.info(`detected ${event} on ${file}; scheduling rescan`);
      if (this.rescanTimer) clearTimeout(this.rescanTimer);
      this.rescanTimer = setTimeout(() => {
        this.refresh().catch(err =>
          this.logger.error(`refresh failed: ${err}`),
        );
      }, 250);
    };

    this.watcher.on('add', f => trigger('add', f));
    this.watcher.on('change', f => trigger('change', f));
    this.watcher.on('unlink', f => trigger('unlink', f));
  }

  private async refresh(): Promise<void> {
    if (!this.connection) return;

    const fileSets = await Promise.all(
      this.watchGlobs.map(g => glob(g, { absolute: true })),
    );
    const files = Array.from(new Set(fileSets.flat()));

    const entities: DeferredEntity[] = [];
    for (const file of files) {
      try {
        const text = await fs.readFile(file, 'utf-8');
        const docs = yaml.loadAll(text);
        const locationRef = `file:${file}`;
        for (const doc of docs) {
          if (!doc || typeof doc !== 'object') continue;
          const raw = doc as {
            kind?: string;
            metadata?: { name?: string; annotations?: Record<string, string> };
          };
          if (!raw.kind || !raw.metadata?.name) continue;
          raw.metadata.annotations = {
            ...(raw.metadata.annotations ?? {}),
            'backstage.io/managed-by-location': locationRef,
            'backstage.io/managed-by-origin-location': locationRef,
          };
          entities.push({
            entity: raw as DeferredEntity['entity'],
            locationKey: `catalog-file-watcher:${file}`,
          });
        }
      } catch (err) {
        this.logger.warn(`failed to parse ${file}: ${err}`);
      }
    }

    await this.connection.applyMutation({ type: 'full', entities });
    this.logger.info(
      `applied full mutation: ${entities.length} entities from ${files.length} files`,
    );
  }

  async dispose(): Promise<void> {
    if (this.rescanTimer) clearTimeout(this.rescanTimer);
    await this.watcher?.close();
  }
}
