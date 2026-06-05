import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { navModule } from './modules/nav';
import { scaffolderOverrides } from './extensions/scaffolder';
import { catalogCardsModule } from './modules/catalog-cards';

export default createApp({
  features: [catalogPlugin, navModule, scaffolderOverrides, catalogCardsModule],
});
