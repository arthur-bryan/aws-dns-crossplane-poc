import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { AwsDnsZonePicker } from './AwsDnsZonePicker';

export const AwsDnsZonePickerExtensionField = createScaffolderFieldExtension({
  name: 'AwsDnsZonePicker',
  component: AwsDnsZonePicker,
});

export const AwsDnsZonePickerExtensionPlugin = scaffolderPlugin.provide(AwsDnsZonePickerExtensionField);
