/*
 * Copyright 2021 The Backstage Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { EntityPicker, EntityPickerSchema } from '../components/fields/EntityPicker/EntityPicker';
import { EntityNamePicker, EntityNamePickerSchema } from '../components/fields/EntityNamePicker/EntityNamePicker';
import { entityNamePickerValidation } from '../components/fields/EntityNamePicker/validation';
import { EntityTagsPicker, EntityTagsPickerSchema } from '../components/fields/EntityTagsPicker/EntityTagsPicker';
import { OwnerPicker, OwnerPickerSchema } from '../components/fields/OwnerPicker/OwnerPicker';
import { RepoUrlPicker, RepoUrlPickerSchema } from '../components/fields/RepoUrlPicker/RepoUrlPicker';
import { repoPickerValidation } from '../components/fields/RepoUrlPicker/validation';
import { OwnedEntityPicker, OwnedEntityPickerSchema } from '../components/fields/OwnedEntityPicker/OwnedEntityPicker';
import { MyGroupsPicker, MyGroupsPickerSchema } from '../components/fields/MyGroupsPicker/MyGroupsPicker';

import { SecretInput } from '../components/fields/SecretInput';
import { SquadAccessUsersField, SquadAccessUsersFieldSchema } from '../components/fields/SquadAccessUsersField';
import { MultiEntityPicker, MultiEntityPickerSchema, validateMultiEntityPickerValidation } from '../components/fields/MultiEntityPicker/MultiEntityPicker';
import { RepoBranchPicker } from '../components/fields/RepoBranchPicker/RepoBranchPicker';
import { RepoBranchPickerSchema } from '../components/fields/RepoBranchPicker/schema';
import { RepoOwnerPicker, RepoOwnerPickerSchema } from '../components/fields/RepoOwnerPicker';
import { EnvironmentPicker, EnvironmentPickerSchema } from '../components/fields/EnvironmentPicker';
import { AwsVpcPicker, AwsVpcPickerSchema } from '../components/fields/AwsVpcPicker';
import { AwsVpcCidrBlockPicker, AwsVpcCidrBlockPickerSchema } from '../components/fields/AwsVpcCidrBlockPicker';
import { AwsSubnetPicker, AwsSubnetPickerSchema } from '../components/fields/AwsSubnetPicker';
import { AwsRolePicker, AwsRolePickerSchema } from '../components/fields/AwsRolePicker';
import { AwsSecretPicker, AwsSecretPickerSchema } from '../components/fields/AwsSecretPicker';
import { EntityNameComposerPicker, EntityNameComposerPickerSchema } from '../components/fields/EntityNameComposerPicker';
import { EntitySpecKeysPicker, EntitySpecKeysPickerSchema } from '../components/fields/EntitySpecKeysPicker';
import { RepositoryNameComposerPicker, RepositoryNameComposerPickerSchema } from '../components/fields/RepositoryNameComposerPicker';
import { RepositorySystemReadonlyField, RepositorySystemReadonlyFieldSchema } from '../components/fields/RepositorySystemReadonlyField';
import { KeyValueField, KeyValueFieldSchema, validateKeyValueField } from '../components/fields/KeyValueField';
import { ManageableSquadPicker, ManageableSquadPickerSchema } from '../components/fields/ManageableSquadPicker';
import { ManageableSquadsPicker, ManageableSquadsPickerSchema } from '../components/fields/ManageableSquadsPicker';
import { AwsPolicyValidatorField, AwsPolicyValidatorFieldSchemaSchema } from '../components/fields/AwsPolicyValidatorField';
import { AwsParentPicker, AwsParentPickerSchema } from '../components/fields/AwsParentPicker';
import { AwsDnsZonePicker, AwsDnsZonePickerSchema } from '../components/fields/AwsDnsZonePicker';
import { AwsDnsRecordPicker, AwsDnsRecordPickerSchema } from '../components/fields/AwsDnsRecordPicker';
import { RecordFqdnPreview, RecordFqdnPreviewSchema } from '../components/fields/RecordFqdnPreview';
import { ZoneFqdnPreview, ZoneFqdnPreviewSchema } from '../components/fields/ZoneFqdnPreview';
import { RecordChangeImpactWarning, RecordChangeImpactWarningSchema } from '../components/fields/RecordChangeImpactWarning';
import { RecordTypeField, RecordTypeFieldSchema } from '../components/fields/RecordTypeField';
import { WeightedWeightField, WeightedWeightFieldSchema } from '../components/fields/WeightedWeightField';
import { WeightedSetIdentifierField, WeightedSetIdentifierFieldSchema } from '../components/fields/WeightedSetIdentifierField';
import {
  RepositorySuffixPicker,
  RepositorySuffixPickerSchema,
  AwsAccountPicker,
  AwsAccountPickerSchema,
  AwsEnvironmentPicker,
  AwsEnvironmentPickerSchema,
  AwsEnvironmentAccountPicker,
  AwsEnvironmentAccountPickerSchema,
  ClusterEnvironmentPicker,
  ClusterEnvironmentPickerSchema,
  SystemEnvironmentClusterPicker,
  SystemEnvironmentClusterPickerSchema,
  AwsRegionPicker,
  AwsRegionPickerSchema,
  YamlField,
  ComponentSystemPicker,
  ComponentSystemPickerSchema,
  ChangePicker,
  ChangePickerSchema,
  EverlastMigrationRepositoryPicker,
  EverlastMigrationRepositoryPickerSchema,
  FieldsGroupExpandToggle,
  FieldsGroupExpandToggleSchema,
  validateFieldsGroupExpandToggleField,
  ContainerPortsField,
  ContainerPortsFieldSchema,
  validateContainerPortsField,
  ContainerPortsSelectField,
  ContainerPortsSelectFieldSchema,
  ContainerResourcesField,
  ContainerResourcesFieldSchema,
  validateContainerResourcesField,
  KubernetesProbesField,
  KubernetesProbesFieldSchema,
  validateKubernetesProbesField,
  KubernetesServiceField,
  KubernetesServiceFieldSchema,
  validateKubernetesServiceField,
} from '../components';
import { validateAwsPolicyField } from '../components/fields/AwsPolicyValidatorField/AwsPolicyValidatorFieldExtension';
import { validateChangePicker } from '../components/fields/ChangePicker/ChangePickerExtension';
import { ConfigMapValidation } from '../components/fields/Yaml/ConfigMapValidation';

export const DEFAULT_SCAFFOLDER_FIELD_EXTENSIONS = [
  {
    component: EntityPicker,
    name: 'EntityPicker',
    schema: EntityPickerSchema,
  },
  {
    component: EntityNamePicker,
    name: 'EntityNamePicker',
    validation: entityNamePickerValidation,
    schema: EntityNamePickerSchema,
  },
  {
    component: EntityTagsPicker,
    name: 'EntityTagsPicker',
    schema: EntityTagsPickerSchema,
  },
  {
    component: RepoUrlPicker,
    name: 'RepoUrlPicker',
    validation: repoPickerValidation,
    schema: RepoUrlPickerSchema,
  },
  {
    component: RepositorySuffixPicker,
    name: 'RepositorySuffixPicker',
    schema: RepositorySuffixPickerSchema,
  },
  {
    component: EntityNameComposerPicker,
    name: 'EntityNameComposerPicker',
    schema: EntityNameComposerPickerSchema,
  },
  {
    component: EntitySpecKeysPicker,
    name: 'EntitySpecKeysPicker',
    schema: EntitySpecKeysPickerSchema,
  },
  {
    component: ManageableSquadPicker,
    name: 'ManageableSquadPicker',
    schema: ManageableSquadPickerSchema,
  },
  {
    component: ManageableSquadsPicker,
    name: 'ManageableSquadsPicker',
    schema: ManageableSquadsPickerSchema,
  },
  {
    component: RepositoryNameComposerPicker,
    name: 'RepositoryNameComposerPicker',
    schema: RepositoryNameComposerPickerSchema,
  },
  {
    component: AwsAccountPicker,
    name: 'AwsAccountPicker',
    schema: AwsAccountPickerSchema,
  },
  {
    component: AwsEnvironmentPicker,
    name: 'AwsEnvironmentPicker',
    schema: AwsEnvironmentPickerSchema,
  },
  {
    component: AwsParentPicker,
    name: 'AwsParentPicker',
    schema: AwsParentPickerSchema,
  },
  {
    component: AwsEnvironmentAccountPicker,
    name: 'AwsEnvironmentAccountPicker',
    schema: AwsEnvironmentAccountPickerSchema,
  },
  {
    component: ClusterEnvironmentPicker,
    name: 'ClusterEnvironmentPicker',
    schema: ClusterEnvironmentPickerSchema,
  },
  {
    component: SystemEnvironmentClusterPicker,
    name: 'SystemEnvironmentClusterPicker',
    schema: SystemEnvironmentClusterPickerSchema,
  },
  {
    component: AwsRegionPicker,
    name: 'AwsRegionPicker',
    schema: AwsRegionPickerSchema,
  },
  {
    component: AwsSecretPicker,
    name: 'AwsSecretPicker',
    schema: AwsSecretPickerSchema,
  },
  {
    component: AwsRolePicker,
    name: 'AwsRolePicker',
    schema: AwsRolePickerSchema,
  },
  {
    component: KeyValueField,
    name: 'KeyValueField',
    schema: KeyValueFieldSchema,
    validation: validateKeyValueField,
  },
  {
    component: ContainerPortsField,
    name: 'ContainerPortsField',
    schema: ContainerPortsFieldSchema,
    validation: validateContainerPortsField,
  },
  {
    component: ContainerPortsSelectField,
    name: 'ContainerPortsSelectField',
    schema: ContainerPortsSelectFieldSchema,
  },
  {
    component: ContainerResourcesField,
    name: 'ContainerResourcesField',
    schema: ContainerResourcesFieldSchema,
    validation: validateContainerResourcesField,
  },
  {
    component: KubernetesProbesField,
    name: 'KubernetesProbesField',
    schema: KubernetesProbesFieldSchema,
    validation: validateKubernetesProbesField,
  },
  {
    component: KubernetesServiceField,
    name: 'KubernetesServiceField',
    schema: KubernetesServiceFieldSchema,
    validation: validateKubernetesServiceField,
  },
  {
    component: OwnerPicker,
    name: 'OwnerPicker',
    schema: OwnerPickerSchema,
  },
  {
    component: OwnedEntityPicker,
    name: 'OwnedEntityPicker',
    schema: OwnedEntityPickerSchema,
  },
  {
    component: MyGroupsPicker,
    name: 'MyGroupsPicker',
    schema: MyGroupsPickerSchema,
  },
  {
    component: SecretInput,
    name: 'Secret',
  },
  {
    component: SquadAccessUsersField,
    name: 'SquadAccessUsersField',
    schema: SquadAccessUsersFieldSchema,
  },
  {
    component: MultiEntityPicker,
    name: 'MultiEntityPicker',
    schema: MultiEntityPickerSchema,
    validation: validateMultiEntityPickerValidation,
  },
  {
    component: RepoBranchPicker,
    name: 'RepoBranchPicker',
    schema: RepoBranchPickerSchema,
  },
  {
    component: RepoOwnerPicker,
    name: 'RepoOwnerPicker',
    schema: RepoOwnerPickerSchema,
  },
  {
    component: YamlField,
    name: 'ConfigMap',
    validation: ConfigMapValidation,
  },
  {
    component: AwsVpcPicker,
    name: 'AwsVpcPicker',
    schema: AwsVpcPickerSchema,
  },
  {
    component: AwsVpcCidrBlockPicker,
    name: 'AwsVpcCidrBlockPicker',
    schema: AwsVpcCidrBlockPickerSchema,
  },
  {
    component: AwsSubnetPicker,
    name: 'AwsSubnetPicker',
    schema: AwsSubnetPickerSchema,
  },
  {
    component: EnvironmentPicker,
    name: 'EnvironmentPicker',
    schema: EnvironmentPickerSchema,
  },
  {
    component: RepositorySystemReadonlyField,
    name: 'RepositorySystemReadonlyField',
    schema: RepositorySystemReadonlyFieldSchema,
  },
  {
    component: ComponentSystemPicker,
    name: 'ComponentSystemPicker',
    schema: ComponentSystemPickerSchema,
  },
  {
    component: AwsPolicyValidatorField,
    name: 'AwsPolicyValidatorField',
    schema: AwsPolicyValidatorFieldSchemaSchema,
    validation: validateAwsPolicyField,
  },
  {
    component: ChangePicker,
    name: 'ChangePicker',
    schema: ChangePickerSchema,
    validation: validateChangePicker,
  },
  {
    component: EverlastMigrationRepositoryPicker,
    name: 'EverlastMigrationRepositoryPicker',
    schema: EverlastMigrationRepositoryPickerSchema,
  },
  {
    component: AwsDnsZonePicker,
    name: 'AwsDnsZonePicker',
    schema: AwsDnsZonePickerSchema,
  },
  {
    component: AwsDnsRecordPicker,
    name: 'AwsDnsRecordPicker',
    schema: AwsDnsRecordPickerSchema,
  },
  {
    component: RecordFqdnPreview,
    name: 'RecordFqdnPreview',
    schema: RecordFqdnPreviewSchema,
  },
  {
    component: ZoneFqdnPreview,
    name: 'ZoneFqdnPreview',
    schema: ZoneFqdnPreviewSchema,
  },
  {
    component: RecordChangeImpactWarning,
    name: 'RecordChangeImpactWarning',
    schema: RecordChangeImpactWarningSchema,
  },
  {
    component: RecordTypeField,
    name: 'RecordTypeField',
    schema: RecordTypeFieldSchema,
  },
  {
    component: WeightedWeightField,
    name: 'WeightedWeightField',
    schema: WeightedWeightFieldSchema,
  },
  {
    component: WeightedSetIdentifierField,
    name: 'WeightedSetIdentifierField',
    schema: WeightedSetIdentifierFieldSchema,
  },
  {
    component: FieldsGroupExpandToggle,
    name: 'FieldsGroupExpandToggle',
    schema: FieldsGroupExpandToggleSchema,
    validation: validateFieldsGroupExpandToggleField,
  },
];
