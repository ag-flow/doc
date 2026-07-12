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
  functionalTypeSlug: string | null
}

/**
 * Construit l'index slug-de-propriété → valeurs autorisées pour LE type du
 * document uniquement. Une propriété `restricted_list` tire ses options du type
 * qui la déclare ; deux types différents peuvent déclarer le même slug (ex.
 * `statut`) avec des valeurs autorisées distinctes. Balayer tous les types dans
 * un index global par slug écraserait les options (dernier type gagne) et
 * présenterait au document les valeurs d'un autre type — un choix alors rejeté
 * par le backend (422 « valeur autorisée introuvable »). On scope donc au type
 * réel du document.
 */
function buildAllowedIndex(
  types: FunctionalTypeWithProps[],
  functionalTypeSlug: string | null,
): Map<string, AllowedValueOut[]> {
  const index = new Map<string, AllowedValueOut[]>()
  const type = types.find((t) => t.slug === functionalTypeSlug)
  if (!type) return index
  for (const def of type.properties ?? []) {
    if (def.type === 'restricted_list' && def.allowed_values) {
      index.set(def.slug, [...def.allowed_values].sort((a, b) => a.position - b.position))
    }
  }
  return index
}

export function PropertiesPanel({ ws, docId, functionalTypeSlug }: PropertiesPanelProps) {
  const { t } = useTranslation()

  const { data: values = [], isLoading } = useQuery<PropertyValueOut[]>({
    queryKey: ['doc-values', ws, docId],
    queryFn: () => docsApi.getDocumentValues(ws, docId),
  })

  const { data: types = [] } = useQuery<FunctionalTypeWithProps[]>({
    queryKey: ['types-rich', ws],
    queryFn: () => api.get(`/workspaces/${ws}/types/rich`),
  })

  const allowedIndex = useMemo(
    () => buildAllowedIndex(types, functionalTypeSlug),
    [types, functionalTypeSlug],
  )

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
