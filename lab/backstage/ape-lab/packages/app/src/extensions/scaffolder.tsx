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
          const { AwsVpcPickerExtensionPlugin } = await import('../modules/scaffolder/AwsVpcPicker/AwsVpcPickerExtension');
          const { RecordFqdnPreviewExtensionPlugin } = await import('../modules/scaffolder/RecordFqdnPreviewExtension');
          const { ZoneFqdnPreviewExtensionPlugin } = await import('../modules/scaffolder/ZoneFqdnPreviewExtension');
          const { EntityNameComposerPickerExtensionPlugin } = await import('../modules/scaffolder/EntityNameComposerPicker/EntityNameComposerPickerExtension');
          const { RecordChangeImpactWarningExtensionPlugin } = await import('../modules/scaffolder/RecordChangeImpactWarningExtension');
          const { ScaffolderTemplateListPage } = await import('./ScaffolderTemplateListPage');
          const { ScaffolderTaskPage } = await import('./ScaffolderTaskPage');
          return (
            <ScaffolderPage
              templateFilter={(e) => !e.metadata.tags?.includes('hidden')}
              components={{
                EXPERIMENTAL_TemplateListPageComponent: ScaffolderTemplateListPage,
                TaskPageComponent: ScaffolderTaskPage,
              }}
              groups={[
                {
                  title: 'AWS Resources',
                  filter: (entity) => entity?.metadata?.tags?.includes('aws') ?? false,
                },
              ]}
            >
              <ScaffolderLayouts />
              <ScaffolderFieldExtensions>
                <EnvironmentPickerExtensionPlugin />
                <AwsDnsZonePickerExtensionPlugin />
                <AwsDnsRecordPickerExtensionPlugin />
                <AwsVpcPickerExtensionPlugin />
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
