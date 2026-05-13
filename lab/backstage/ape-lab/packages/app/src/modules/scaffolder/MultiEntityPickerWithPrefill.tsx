import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  CircularProgress,
  FormHelperText,
  TextField,
  makeStyles,
} from '@material-ui/core';
import { Autocomplete } from '@material-ui/lab';
import { useApi } from '@backstage/core-plugin-api';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import { parseEntityRef, stringifyEntityRef } from '@backstage/catalog-model';
import type { Entity } from '@backstage/catalog-model';
import type { FieldExtensionComponentProps } from '@backstage/plugin-scaffolder-react';

type CatalogFilterRow = Record<string, string | string[]>;

type Options = {
  entityRefField?: string;
  catalogFilter?: CatalogFilterRow[];
};

const useStyles = makeStyles(theme => ({
  helper: { marginTop: theme.spacing(0.5) },
}));

const refOf = (entity: Entity): string =>
  stringifyEntityRef({
    kind: entity.kind,
    namespace: entity.metadata.namespace ?? 'default',
    name: entity.metadata.name,
  });

const labelOf = (entity: Entity): string => {
  const annotations = entity.metadata.annotations ?? {};
  const vpcId = annotations['dock.tech/vpc-id'];
  const vpcRegion = annotations['dock.tech/vpc-region'];
  const accountName = annotations['dock.tech/aws-account-name'];
  const base = entity.metadata.title ?? entity.metadata.name;
  const facets: string[] = [];
  if (vpcId) facets.push(vpcId);
  if (vpcRegion) facets.push(vpcRegion);
  if (accountName) facets.push(accountName);
  return facets.length ? `${base} (${facets.join(' · ')})` : base;
};

const labelOfRef = (ref: string, byRef: Map<string, Entity>): string => {
  const e = byRef.get(ref);
  return e ? labelOf(e) : ref;
};

const flattenFilter = (
  rows: CatalogFilterRow[] | undefined,
): Record<string, string | string[]> => {
  if (!rows || rows.length === 0) return {};
  const out: Record<string, string | string[]> = {};
  for (const row of rows) {
    for (const [k, v] of Object.entries(row)) {
      out[k] = v as string | string[];
    }
  }
  return out;
};

const parseSnapshotVpcs = (snapshotJson: string | undefined): string[] => {
  if (!snapshotJson) return [];
  try {
    const parsed = JSON.parse(snapshotJson);
    if (parsed && Array.isArray(parsed.vpcs)) {
      return parsed.vpcs.filter((x: unknown): x is string => typeof x === 'string');
    }
  } catch {
    /* ignore malformed snapshot — the form just renders empty */
  }
  return [];
};

export const MultiEntityPickerWithPrefill = (
  props: FieldExtensionComponentProps<string[]>,
) => {
  const classes = useStyles();
  const catalogApi = useApi(catalogApiRef);
  const { onChange, formData, uiSchema, rawErrors, required, formContext } = props;
  const options = ((uiSchema && uiSchema['ui:options']) ?? {}) as Options;
  const entityRefField = options.entityRefField ?? 'zone';
  const catalogFilter = useMemo(
    () => flattenFilter(options.catalogFilter),
    [options.catalogFilter],
  );

  const rootFormData = ((formContext as { formData?: Record<string, unknown> })?.formData ??
    {}) as Record<string, unknown>;
  const sourceEntityRef = rootFormData[entityRefField];
  const sourceRef = typeof sourceEntityRef === 'string' ? sourceEntityRef : undefined;

  const [allVpcEntities, setAllVpcEntities] = useState<Entity[]>([]);
  const [byRef, setByRef] = useState<Map<string, Entity>>(new Map());
  const [loading, setLoading] = useState<boolean>(true);
  const [prefilled, setPrefilled] = useState<boolean>(false);

  // Load the VPC option list once.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    catalogApi
      .getEntities({ filter: catalogFilter })
      .then(({ items }) => {
        if (cancelled) return;
        const map = new Map<string, Entity>();
        for (const e of items) map.set(refOf(e), e);
        setAllVpcEntities(items);
        setByRef(map);
      })
      .catch(() => {
        if (cancelled) return;
        setAllVpcEntities([]);
        setByRef(new Map());
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [catalogApi, catalogFilter]);

  // Prefill from the picked source entity's scaffolder-parameters annotation.
  // Only runs once, when both the source ref is known and the user hasn't
  // already started editing the picker.
  useEffect(() => {
    if (prefilled || !sourceRef) return;
    let cancelled = false;
    (async () => {
      try {
        const parsed = parseEntityRef(sourceRef, {
          defaultKind: 'Resource',
          defaultNamespace: 'default',
        });
        const entity = await catalogApi.getEntityByRef(parsed);
        if (cancelled || !entity) return;
        const snapshot =
          entity.metadata.annotations?.['dock.tech/scaffolder-parameters'];
        const refs = parseSnapshotVpcs(snapshot);
        if (refs.length === 0) {
          setPrefilled(true);
          return;
        }
        // Only set if formData is still empty (avoid clobbering user edits or
        // a URL-supplied formData prefill).
        const currentLen = Array.isArray(formData) ? formData.length : 0;
        if (currentLen === 0) onChange(refs);
        setPrefilled(true);
      } catch {
        setPrefilled(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sourceRef, prefilled, catalogApi, onChange, formData]);

  const selectedRefs: string[] = Array.isArray(formData) ? formData : [];

  const handleChange = useCallback(
    (_: unknown, newValue: Entity[]) => {
      onChange(newValue.map(refOf));
    },
    [onChange],
  );

  if (loading) {
    return (
      <Box display="flex" alignItems="center" gridGap={12} my={1}>
        <CircularProgress size={18} />
        <span>Loading VPCs…</span>
      </Box>
    );
  }

  const selectedEntities = selectedRefs
    .map(r => byRef.get(r))
    .filter((e): e is Entity => Boolean(e));

  return (
    <Box my={1}>
      <Autocomplete
        multiple
        options={allVpcEntities}
        getOptionLabel={labelOf}
        getOptionSelected={(opt, val) => refOf(opt) === refOf(val)}
        value={selectedEntities}
        onChange={handleChange}
        disableCloseOnSelect
        renderInput={params => (
          <TextField
            {...params}
            label="Associated VPCs"
            placeholder="Add a VPC…"
            variant="outlined"
            required={required}
            error={Boolean(rawErrors && rawErrors.length)}
          />
        )}
      />
      <FormHelperText className={classes.helper}>
        Add or remove any VPC. AWS will reject an edit that would leave the
        zone with zero associations (the last VPC cannot be disassociated).
        {rawErrors && rawErrors.length ? ` · ${rawErrors[0]}` : ''}
      </FormHelperText>
    </Box>
  );
};
