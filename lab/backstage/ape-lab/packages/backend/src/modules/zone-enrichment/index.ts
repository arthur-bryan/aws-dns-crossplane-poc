import { coreServices, createBackendModule } from '@backstage/backend-plugin-api';
import { catalogProcessingExtensionPoint } from '@backstage/plugin-catalog-node';
import { DockZoneEnrichmentProcessor } from './DockZoneEnrichmentProcessor';

export const catalogModuleZoneEnrichment = createBackendModule({
  pluginId: 'catalog',
  moduleId: 'dock-zone-enrichment',
  register(env) {
    env.registerInit({
      deps: {
        catalog: catalogProcessingExtensionPoint,
        logger: coreServices.logger,
      },
      async init({ catalog, logger }) {
        catalog.addProcessor(new DockZoneEnrichmentProcessor({ logger }));
      },
    });
  },
});

export default catalogModuleZoneEnrichment;
