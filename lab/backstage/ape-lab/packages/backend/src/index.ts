import { createBackend } from '@backstage/backend-defaults';

const backend = createBackend();

backend.add(import('@backstage/plugin-app-backend'));
backend.add(import('@backstage/plugin-proxy-backend'));

backend.add(import('@backstage/plugin-scaffolder-backend'));
backend.add(import('@backstage/plugin-scaffolder-backend-module-github'));
backend.add(
  import('@backstage/plugin-scaffolder-backend-module-notifications'),
);

backend.add(import('@roadiehq/scaffolder-backend-module-utils'));

backend.add(import('@backstage/plugin-techdocs-backend'));

backend.add(import('@backstage/plugin-auth-backend'));
backend.add(import('@backstage/plugin-auth-backend-module-guest-provider'));

backend.add(import('@backstage/plugin-catalog-backend'));
backend.add(
  import('@backstage/plugin-catalog-backend-module-scaffolder-entity-model'),
);

backend.add(import('@backstage/plugin-catalog-backend-module-logs'));

backend.add(import('./modules/zone-enrichment'));
// Hybrid catalog sourcing:
//   - Static seed (Domain/System/Group/environments + Templates) comes from
//     remote URLs in catalog.locations, so it tracks GitHub without any
//     local-clone dependency.
//   - Dynamic per-zone / per-record YAMLs under entities/catalog/**/*.yaml
//     are picked up by this chokidar watcher against the local clone. We
//     tried the official GitHub catalog provider, but Backstage's branch
//     parser rejects '/' in filters.branch and the URL reader mishandles
//     blob<->tree path translation for branches with slashes. Until the
//     branch is renamed or Backstage fixes those, the file watcher + the
//     30s git-pull poller (backstage-up.sh) provide the same behaviour
//     end-to-end: new catalog files appear ~30-60s after a PR is merged.
backend.add(import('./modules/catalog-file-watcher'));
backend.add(import('./modules/dns-routes'));
backend.add(import('./modules/github-extras-actions'));

backend.add(import('@backstage/plugin-permission-backend'));
backend.add(
  import('@backstage/plugin-permission-backend-module-allow-all-policy'),
);

backend.add(import('@backstage/plugin-search-backend'));

backend.add(import('@backstage/plugin-search-backend-module-pg'));

backend.add(import('@backstage/plugin-search-backend-module-catalog'));
backend.add(import('@backstage/plugin-search-backend-module-techdocs'));

backend.add(import('@backstage/plugin-kubernetes-backend'));

backend.add(import('@backstage/plugin-notifications-backend'));
backend.add(import('@backstage/plugin-signals-backend'));

backend.add(import('@backstage/plugin-mcp-actions-backend'));

backend.start();
