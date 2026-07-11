import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { docsApi, type AllowedValueOut, type PropertyValueOut } from '../lib/api'
import { PropertyField } from './PropertyField'

interface Props {
  ws: string
  docId: string
  propSlug: string
  propType: string
  /** Valeur brute affichée (scalaires) — null si non renseignée. */
  value: string | null
  /** Slug de valeur autorisée (restricted_list) — null si non renseignée. */
  allowedSlug: string | null
  /** Valeurs autorisées **scopées au type du document** (pill + options d'édition). */
  allowedValues: AllowedValueOut[]
  /** Faux pour les propriétés à comportement auto (lecture seule) : pas d'édition. */
  editable: boolean
  /** Rafraîchit la table après une sauvegarde réussie. */
  onSaved: () => void
}

function Pill({ label, color }: { label: string; color: string | null }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      style={color ? { backgroundColor: color, color: '#fff' } : { backgroundColor: '#e5e7eb', color: '#374151' }}
    >
      {label}
    </span>
  )
}

/** Cellule de propriété éditable en place : vue lecture (pill/texte) → contrôle
 *  inline au clic, réutilisant `PropertyField` (auto-save + conflit) en mode
 *  compact. La version courante est récupérée à l'ouverture via `getDocumentValues`
 *  (concurrence optimiste correcte) ; les valeurs autorisées sont scopées au type
 *  du document pour éviter tout 422 sur liste fermée. */
export function InlinePropertyCell({
  ws,
  docId,
  propSlug,
  propType,
  value,
  allowedSlug,
  allowedValues,
  editable,
  onSaved,
}: Props) {
  const [editing, setEditing] = useState(false)

  const { data: values } = useQuery<PropertyValueOut[]>({
    queryKey: ['doc-values', ws, docId],
    queryFn: () => docsApi.getDocumentValues(ws, docId),
    enabled: editing,
  })

  const isEmpty = value === null && !allowedSlug
  const readView =
    propType === 'restricted_list' ? (
      allowedSlug ? (
        (() => {
          const av = allowedValues.find((a) => a.slug === allowedSlug)
          return <Pill label={av?.label ?? allowedSlug} color={av?.color ?? null} />
        })()
      ) : (
        <span className="text-gray-300">—</span>
      )
    ) : isEmpty ? (
      <span className="text-gray-300">—</span>
    ) : (
      <span className="text-sm">{value}</span>
    )

  if (!editable) return readView

  if (!editing) {
    return (
      <button
        type="button"
        className="cursor-pointer text-left hover:bg-gray-100 rounded px-1 -mx-1"
        onClick={(e) => {
          e.stopPropagation()
          setEditing(true)
        }}
        data-testid={`inline-cell-${propSlug}-${docId}`}
      >
        {readView}
      </button>
    )
  }

  const prop: PropertyValueOut = values?.find((v) => v.prop_slug === propSlug) ?? {
    prop_slug: propSlug,
    prop_label: propSlug,
    type: propType as PropertyValueOut['type'],
    version: null,
    value,
    allowed_value_slug: allowedSlug,
    allowed_value_label: null,
    required: false,
    behavior: null,
  }

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setEditing(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setEditing(false)
      }}
      data-testid={`inline-edit-${propSlug}-${docId}`}
    >
      {values === undefined ? (
        <span className="text-xs text-gray-400">…</span>
      ) : (
        <PropertyField
          ws={ws}
          docId={docId}
          prop={prop}
          allowedValues={allowedValues}
          compact
          onSaved={() => {
            onSaved()
            setEditing(false)
          }}
        />
      )}
    </div>
  )
}
