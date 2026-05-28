import { createFrontendModule } from '@backstage/frontend-plugin-api';
import {
  FormFieldBlueprint,
  createFormField,
} from '@backstage/plugin-scaffolder-react/alpha';
import { z } from 'zod';
import { ZoneFqdnPreview } from './ZoneFqdnPreview';
import { RecordFqdnPreview } from './RecordFqdnPreview';
import { EnvironmentPicker } from './EnvironmentPicker';
import { AwsDnsZonePicker } from './AwsDnsZonePicker/AwsDnsZonePicker';
import { AwsDnsRecordPicker } from './AwsDnsRecordPicker/AwsDnsRecordPicker';

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

const environmentPickerField = FormFieldBlueprint.make({
  name: 'environment-picker',
  params: {
    field: async () =>
      createFormField({
        name: 'EnvironmentPicker',
        component: EnvironmentPicker,
        schema: {
          returnValue: z.enum(['dev', 'hml', 'prd']).optional(),
        },
      }),
  },
});

const awsDnsZonePickerField = FormFieldBlueprint.make({
  name: 'aws-dns-zone-picker',
  params: {
    field: async () =>
      createFormField({
        name: 'AwsDnsZonePicker',
        component: AwsDnsZonePicker,
        schema: {
          returnValue: z
            .object({ id: z.string(), name: z.string() })
            .optional(),
        },
      }),
  },
});

const awsDnsRecordPickerField = FormFieldBlueprint.make({
  name: 'aws-dns-record-picker',
  params: {
    field: async () =>
      createFormField({
        name: 'AwsDnsRecordPicker',
        component: AwsDnsRecordPicker,
        schema: {
          returnValue: z.any().optional(),
        },
      }),
  },
});

export const scaffolderModule = createFrontendModule({
  pluginId: 'scaffolder',
  extensions: [
    zoneFqdnPreviewField,
    recordFqdnPreviewField,
    environmentPickerField,
    awsDnsZonePickerField,
    awsDnsRecordPickerField,
  ],
});
