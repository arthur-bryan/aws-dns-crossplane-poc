import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { RecordChangeImpactWarning } from './RecordChangeImpactWarning';

export const RecordChangeImpactWarningExtensionField = createScaffolderFieldExtension({
  name: 'RecordChangeImpactWarning',
  component: RecordChangeImpactWarning,
});

export const RecordChangeImpactWarningExtensionPlugin = scaffolderPlugin.provide(
  RecordChangeImpactWarningExtensionField,
);
