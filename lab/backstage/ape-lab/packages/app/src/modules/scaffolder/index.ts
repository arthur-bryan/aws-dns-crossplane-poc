import { createFrontendModule } from '@backstage/frontend-plugin-api';
import {
  FormFieldBlueprint,
  createFormField,
} from '@backstage/plugin-scaffolder-react/alpha';
import { z } from 'zod';
import { ZoneFqdnPreview } from './ZoneFqdnPreview';

const zoneFqdnPreviewField = FormFieldBlueprint.make({
  name: 'zone-fqdn-preview',
  params: {
    field: async () =>
      createFormField({
        name: 'ZoneFqdnPreview',
        component: ZoneFqdnPreview,
        schema: {
          returnValue: z.string().optional(),
        },
      }),
  },
});

export const scaffolderModule = createFrontendModule({
  pluginId: 'scaffolder',
  extensions: [zoneFqdnPreviewField],
});
