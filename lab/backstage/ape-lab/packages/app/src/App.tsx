import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { navModule } from './modules/nav';
import { scaffolderModule } from './modules/scaffolder';
import { catalogCardsModule } from './modules/catalog-cards';

export default createApp({
  features: [catalogPlugin, navModule, scaffolderModule, catalogCardsModule],
});
