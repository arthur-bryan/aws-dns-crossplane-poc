import { createFrontendModule } from '@backstage/frontend-plugin-api';
import {
  FormFieldBlueprint,
  createFormField,
} from '@backstage/plugin-scaffolder-react/alpha';
import { z } from 'zod';
import { ZoneFqdnPreview } from './ZoneFqdnPreview';
import { RecordFqdnPreview } from './RecordFqdnPreview';
import { MultiEntityPickerWithPrefill } from './MultiEntityPickerWithPrefill';

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

const multiEntityPickerWithPrefillField = FormFieldBlueprint.make({
  name: 'multi-entity-picker-with-prefill',
  params: {
    field: async () =>
      createFormField({
        name: 'MultiEntityPickerWithPrefill',
        component: MultiEntityPickerWithPrefill,
        schema: {
          returnValue: z.array(z.string()),
        },
      }),
  },
});

export const scaffolderModule = createFrontendModule({
  pluginId: 'scaffolder',
  extensions: [
    zoneFqdnPreviewField,
    recordFqdnPreviewField,
    multiEntityPickerWithPrefillField,
  ],
});
