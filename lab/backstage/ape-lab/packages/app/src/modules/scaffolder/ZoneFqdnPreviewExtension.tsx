import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { ZoneFqdnPreview } from './ZoneFqdnPreview';

export const ZoneFqdnPreviewExtensionField = createScaffolderFieldExtension({
  name: 'ZoneFqdnPreview',
  component: ZoneFqdnPreview,
});

export const ZoneFqdnPreviewExtensionPlugin = scaffolderPlugin.provide(ZoneFqdnPreviewExtensionField);
