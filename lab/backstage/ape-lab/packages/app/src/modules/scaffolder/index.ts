import { createFrontendModule } from '@backstage/frontend-plugin-api';
import {
  FormFieldBlueprint,
  createFormField,
} from '@backstage/plugin-scaffolder-react/alpha';
import { z } from 'zod';
import { ZoneFqdnPreview } from './ZoneFqdnPreview';
import { RecordFqdnPreview } from './RecordFqdnPreview';

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

const recordFqdnPreviewField = FormFieldBlueprint.make({
  name: 'record-fqdn-preview',
  params: {
    field: async () =>
      createFormField({
        name: 'RecordFqdnPreview',
        component: RecordFqdnPreview,
        schema: {
          returnValue: z.string().optional(),
        },
      }),
  },
});

export const scaffolderModule = createFrontendModule({
  pluginId: 'scaffolder',
  extensions: [zoneFqdnPreviewField, recordFqdnPreviewField],
});
