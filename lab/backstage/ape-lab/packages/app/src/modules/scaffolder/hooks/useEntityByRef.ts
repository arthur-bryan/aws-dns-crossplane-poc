import { Entity } from '@backstage/catalog-model';
import { useApi } from '@backstage/core-plugin-api';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import useAsync from 'react-use/esm/useAsync';

type UseEntityByRefOptions = {
  entityRef?: string;
};

type UseEntityByRefResult = {
  entity?: Entity;
  loading: boolean;
  error?: Error;
};

export const useEntityByRef = ({ entityRef }: UseEntityByRefOptions): UseEntityByRefResult => {
  const catalogApi = useApi(catalogApiRef);
  const trimmedEntityRef = entityRef?.trim();

  const {
    value: entity,
    loading,
    error,
  } = useAsync(async () => {
    if (!trimmedEntityRef) {
      return undefined;
    }
    return await catalogApi.getEntityByRef(trimmedEntityRef);
  }, [catalogApi, trimmedEntityRef]);

  return { entity, loading, error };
};
