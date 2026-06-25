import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { RecordFqdnPreview } from './RecordFqdnPreview';

export const RecordFqdnPreviewExtensionField = createScaffolderFieldExtension({
  name: 'RecordFqdnPreview',
  component: RecordFqdnPreview,
});

export const RecordFqdnPreviewExtensionPlugin = scaffolderPlugin.provide(RecordFqdnPreviewExtensionField);
