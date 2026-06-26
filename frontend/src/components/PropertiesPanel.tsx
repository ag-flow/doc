import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  docsApi,
  type AllowedValueOut,
  type FunctionalTypeWithProps,
  type PropertyValueOut,
} from '../lib/api'
import { api } from '../lib/api'
import { PropertyField } from './PropertyField'

interface PropertiesPanelProps {
  ws: string
  docId: string
}

/**
 * Construit l'index slug-de-propriété → valeurs autorisées, à partir des
 * définitions de types (une propriété `restricted_list` tire ses options du
 * type qui la déclare).
 */
function buildAllowedIndex(
  types: FunctionalTypeWithProps[],
): Map<string, AllowedValueOut[]> {
  const index = new Map<string, AllowedValueOut[]>()
  for (const type of types) {
    for (const def of type.properties ?? []) {
      if (def.type === 'restricted_list' && def.allowed_values) {
        index.set(def.slug, [...def.allowed_values].sort((a, b) => a.position - b.position))
      }
    }
  }
  return index
}

export function PropertiesPanel({ ws, docId }: PropertiesPanelProps) {
  const { t } = useTranslation()

  const { data: values = [], isLoading } = useQuery<PropertyValueOut[]>({
    queryKey: ['doc-values', ws, docId],
    queryFn: () => docsApi.getDocumentValues(ws, docId),
  })

  const { data: types = [] } = useQuery<FunctionalTypeWithProps[]>({
    queryKey: ['types', ws],
    queryFn: () => api.get(`/workspaces/${ws}/types`),
  })

  const allowedIndex = useMemo(() => buildAllowedIndex(types), [types])

  return (
    <aside className="w-full" data-testid="properties-panel">
      <h2 className="mb-4 text-sm font-semibold tracking-wide text-gray-500 uppercase">
        {t('properties.title')}
      </h2>
      {isLoading ? (
        <p className="text-sm text-gray-400">{t('common.loading')}</p>
      ) : values.length === 0 ? (
        <p className="text-sm text-gray-400">{t('properties.empty')}</p>
      ) : (
        values.map((prop) => (
          <PropertyField
            key={prop.prop_slug}
            ws={ws}
            docId={docId}
            prop={prop}
            allowedValues={allowedIndex.get(prop.prop_slug) ?? []}
          />
        ))
      )}
    </aside>
  )
}
