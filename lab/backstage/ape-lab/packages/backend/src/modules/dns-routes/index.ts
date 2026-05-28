import {
  coreServices,
  createBackendPlugin,
} from '@backstage/backend-plugin-api';
import { createDnsRouter } from './router';

export const dnsPlugin = createBackendPlugin({
  pluginId: 'aws',
  register(env) {
    env.registerInit({
      deps: {
        logger: coreServices.logger,
        config: coreServices.rootConfig,
        httpRouter: coreServices.httpRouter,
      },
      async init({ logger, config, httpRouter }) {
        httpRouter.use(await createDnsRouter({ logger, config }));
        httpRouter.addAuthPolicy({
          path: '/dns-zones',
          allow: 'unauthenticated',
        });
        httpRouter.addAuthPolicy({
          path: '/dns-records',
          allow: 'unauthenticated',
        });
      },
    });
  },
});

export default dnsPlugin;
