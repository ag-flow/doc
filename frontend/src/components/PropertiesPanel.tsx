import { useLayoutEffect, useMemo, useRef, useState } from 'react'
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
  /** Lecture seule : valeurs affichées en texte, aucun champ de saisie. */
  readOnly?: boolean
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

/** Valeur texte longue plafonnée à `lines` lignes, dépliable si elle déborde.
 *  Le débordement est mesuré après rendu (scrollHeight vs clientHeight). */
function ClampText({ text, lines = 5 }: { text: string; lines?: number }) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setOverflows(el.scrollHeight - el.clientHeight > 1)
  }, [text])

  return (
    <div>
      <div
        ref={ref}
        className={expanded ? undefined : 'doc-prop-clamp'}
        style={expanded ? undefined : ({ '--clamp-lines': lines } as React.CSSProperties)}
        data-testid="clamp-text"
      >
        {text}
      </div>
      {(overflows || expanded) && (
        <button
          type="button"
          className="doc-prop-more"
          onClick={() => setExpanded((v) => !v)}
          data-testid="clamp-toggle"
        >
          {expanded ? t('properties.seeLess', 'voir moins') : t('properties.seeMore', 'voir plus')}
        </button>
      )}
    </div>
  )
}

/** Une valeur en texte : la lecture n'expose aucun contrôle de saisie. */
function PropertyReadRow({
  prop,
  allowedValues,
}: {
  prop: PropertyValueOut
  allowedValues: AllowedValueOut[]
}) {
  const { t } = useTranslation()
  const color = prop.allowed_value_slug
    ? allowedValues.find((a) => a.slug === prop.allowed_value_slug)?.color
    : undefined
  let display: React.ReactNode = '—'
  if (prop.type === 'restricted_list') {
    display = prop.allowed_value_label ?? prop.allowed_value_slug ?? '—'
  } else if (prop.type === 'bool') {
    display = prop.value == null ? '—' : prop.value === 'true' ? t('common.yes', 'Oui') : t('common.no', 'Non')
  } else if (prop.type === 'url' && prop.value) {
    display = (
      <a href={prop.value} target="_blank" rel="noopener noreferrer">
        {prop.value}
      </a>
    )
  } else if (prop.value != null && prop.value !== '') {
    // Texte libre potentiellement long : plafonné à 5 lignes, dépliable.
    display = <ClampText text={prop.value} />
  }
  return (
    <div className="mb-3.5" data-testid={`property-read-${prop.prop_slug}`}>
      <div className="doc-prop-label">{prop.prop_label}</div>
      <div className="flex items-start gap-2 text-[14px] text-ink/[0.85]">
        <div className="min-w-0 flex-1 break-words">{display}</div>
        {color && (
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: color }}
            title={prop.allowed_value_label ?? undefined}
            data-testid={`property-color-${prop.prop_slug}`}
          />
        )}
      </div>
    </div>
  )
}

export function PropertiesPanel({ ws, docId, functionalTypeSlug, readOnly = false }: PropertiesPanelProps) {
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
      <h2 className="doc-aside-kicker">
        {t('properties.title')}
      </h2>
      {isLoading ? (
        <p className="text-sm text-gray-400">{t('common.loading')}</p>
      ) : values.length === 0 ? (
        <p className="text-sm text-gray-400">{t('properties.empty')}</p>
      ) : (
        values.map((prop) =>
          readOnly ? (
            <PropertyReadRow
              key={prop.prop_slug}
              prop={prop}
              allowedValues={allowedIndex.get(prop.prop_slug) ?? []}
            />
          ) : (
            <PropertyField
              key={prop.prop_slug}
              ws={ws}
              docId={docId}
              prop={prop}
              allowedValues={allowedIndex.get(prop.prop_slug) ?? []}
            />
          ),
        )
      )}
    </aside>
  )
}
