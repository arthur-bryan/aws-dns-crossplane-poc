import { createFrontendModule } from '@backstage/frontend-plugin-api';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';

export const scaffolderOverrides = createFrontendModule({
  pluginId: 'scaffolder',
  extensions: [
    scaffolderPlugin.getExtension('page:scaffolder').override({
      params: {
        loader: async () => {
          const { ScaffolderPage, ScaffolderLayouts, ScaffolderFieldExtensions } = await import('@backstage/plugin-scaffolder');
          const { EnvironmentPickerExtensionPlugin } = await import('../modules/scaffolder/EnvironmentPickerExtension');
          const { AwsDnsZonePickerExtensionPlugin } = await import('../modules/scaffolder/AwsDnsZonePicker/AwsDnsZonePickerExtension');
          const { AwsDnsRecordPickerExtensionPlugin } = await import('../modules/scaffolder/AwsDnsRecordPicker/AwsDnsRecordPickerExtension');
          const { RecordFqdnPreviewExtensionPlugin } = await import('../modules/scaffolder/RecordFqdnPreviewExtension');
          const { ZoneFqdnPreviewExtensionPlugin } = await import('../modules/scaffolder/ZoneFqdnPreviewExtension');
          const { EntityNameComposerPickerExtensionPlugin } = await import('../modules/scaffolder/EntityNameComposerPicker/EntityNameComposerPickerExtension');
          const { RecordChangeImpactWarningExtensionPlugin } = await import('../modules/scaffolder/RecordChangeImpactWarningExtension');
          return (
            <ScaffolderPage>
              <ScaffolderLayouts />
              <ScaffolderFieldExtensions>
                <EnvironmentPickerExtensionPlugin />
                <AwsDnsZonePickerExtensionPlugin />
                <AwsDnsRecordPickerExtensionPlugin />
                <RecordFqdnPreviewExtensionPlugin />
                <ZoneFqdnPreviewExtensionPlugin />
                <EntityNameComposerPickerExtensionPlugin />
                <RecordChangeImpactWarningExtensionPlugin />
              </ScaffolderFieldExtensions>
            </ScaffolderPage>
          );
        },
      },
    }),
  ],
});
