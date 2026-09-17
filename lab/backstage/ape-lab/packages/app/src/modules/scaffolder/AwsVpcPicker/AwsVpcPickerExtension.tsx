import { scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { createScaffolderFieldExtension } from '@backstage/plugin-scaffolder-react';

import { AwsVpcPicker } from './AwsVpcPicker';

export const AwsVpcPickerExtensionField = createScaffolderFieldExtension({
  name: 'AwsVpcPicker',
  component: AwsVpcPicker,
});

export const AwsVpcPickerExtensionPlugin = scaffolderPlugin.provide(AwsVpcPickerExtensionField);
