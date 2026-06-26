import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { EntityNameComposerPicker } from './EntityNameComposerPicker';

export const EntityNameComposerPickerExtensionField = createScaffolderFieldExtension({
  name: 'EntityNameComposerPicker',
  component: EntityNameComposerPicker,
});

export const EntityNameComposerPickerExtensionPlugin = scaffolderPlugin.provide(EntityNameComposerPickerExtensionField);
