import {
  coreServices,
  createBackendModule,
} from '@backstage/backend-plugin-api';
import { catalogProcessingExtensionPoint } from '@backstage/plugin-catalog-node';
import * as path from 'path';
import { CatalogFileWatcherEntityProvider } from './CatalogFileWatcherEntityProvider';

export const catalogModuleFileWatcher = createBackendModule({
  pluginId: 'catalog',
  moduleId: 'file-watcher',
  register(env) {
    env.registerInit({
      deps: {
        catalog: catalogProcessingExtensionPoint,
        logger: coreServices.logger,
      },
      async init({ catalog, logger }) {
        const repoRoot = path.resolve(process.cwd(), '../../../../..');
        const watchGlobs = [
          path.join(repoRoot, 'entities/catalog/**/*.yaml'),
        ];
        catalog.addEntityProvider(
          new CatalogFileWatcherEntityProvider({ watchGlobs, logger }),
        );
        logger.info(
          `registered catalog file-watcher on: ${watchGlobs.join(', ')}`,
        );
      },
    });
  },
});

export default catalogModuleFileWatcher;
