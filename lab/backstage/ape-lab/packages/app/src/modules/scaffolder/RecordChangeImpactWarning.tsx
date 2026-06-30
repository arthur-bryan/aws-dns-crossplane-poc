import { Alert } from '@material-ui/lab';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

import { useEntityByRef } from './hooks/useEntityByRef';

const isSet = (v: unknown): boolean =>
  typeof v === 'string' && v.trim() !== '';

const mrType = (t?: string): string => (t === 'ALIAS' ? 'A' : t ?? '');

function wouldRequireReplace(
  newType: string | undefined,
  newEnableWeighted: boolean | undefined,
  newSetId: string | undefined,
  existingType: string | undefined,
  existingSetId: string | undefined,
): boolean {
  const newWeighted = newEnableWeighted === true;
  const existingWeighted = isSet(existingSetId);
  const typeChanged = mrType(newType) !== mrType(existingType);
  const weightedToggled = newWeighted !== existingWeighted;
  const setIdChanged =
    newWeighted &&
    existingWeighted &&
    (newSetId ?? '') !== (existingSetId ?? '');
  return typeChanged || weightedToggled || setIdChanged;
}

export const RecordChangeImpactWarning = (
  props: FieldExtensionComponentProps<string>,
) => {
  const ctx = (props.formContext ?? {}) as { formData?: Record<string, any> };
  const data = ctx.formData ?? {};

  const entityRef = data.entityRef as string | undefined;
  const { entity, loading } = useEntityByRef({ entityRef });

  if (loading || !entity) return null;

  const spec = (entity as any).spec ?? {};
  const existingType = spec.recordType as string | undefined;
  const existingSetId = spec.setIdentifier as string | undefined;

  const newType = data.type as string | undefined;
  const newEnableWeighted = data.enableWeightedRouting as boolean | undefined;
  const newSetId = data.setIdentifier as string | undefined;

  if (
    !wouldRequireReplace(
      newType,
      newEnableWeighted,
      newSetId,
      existingType,
      existingSetId,
    )
  ) {
    return null;
  }

  return (
    <Alert
      severity="warning"
      style={{ marginTop: 8, marginBottom: 8 }}
    >
      This change requires the DNS record to be recreated. Expect brief
      unavailability (typically a few seconds, up to a couple of minutes)
      for clients whose DNS cache expires during the change. If this matters
      for your service, schedule the edit during a maintenance window.
    </Alert>
  );
};
