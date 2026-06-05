import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';

const zoneCard = EntityCardBlueprint.make({
  name: 'dns-zone-info',
  params: {
    filter: { kind: 'resource', 'spec.type': 'dns-zone' },
    type: 'info',
    loader: () =>
      import('./ZoneInfoCard').then(m => <m.ZoneInfoCard />),
  },
});

const recordCard = EntityCardBlueprint.make({
  name: 'dns-record-info',
  params: {
    filter: { kind: 'resource', 'spec.type': 'dns-record' },
    type: 'info',
    loader: () =>
      import('./RecordInfoCard').then(m => <m.RecordInfoCard />),
  },
});

export const catalogCardsModule = createFrontendModule({
  pluginId: 'catalog',
  extensions: [zoneCard, recordCard],
});

export default catalogCardsModule;
