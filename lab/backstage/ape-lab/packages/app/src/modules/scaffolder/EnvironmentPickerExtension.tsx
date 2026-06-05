import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { EnvironmentPicker } from './EnvironmentPicker';

export const EnvironmentPickerExtensionField = createScaffolderFieldExtension({
  name: 'EnvironmentPicker',
  component: EnvironmentPicker,
});

export const EnvironmentPickerExtensionPlugin = scaffolderPlugin.provide(EnvironmentPickerExtensionField);
