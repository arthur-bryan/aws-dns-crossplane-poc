import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { AwsDnsRecordPicker } from './AwsDnsRecordPicker';

export const AwsDnsRecordPickerExtensionField = createScaffolderFieldExtension({
  name: 'AwsDnsRecordPicker',
  component: AwsDnsRecordPicker,
});

export const AwsDnsRecordPickerExtensionPlugin = scaffolderPlugin.provide(AwsDnsRecordPickerExtensionField);
