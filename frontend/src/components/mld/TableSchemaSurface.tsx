/**
 * Surface d'édition d'une entité `table-schema` (épic MLD — F7).
 *
 * Une entité s'édite dans une **grille de champs** — une ligne par champ, les
 * colonnes qui comptent — et sa **description passe en panneau latéral** :
 * c'est un texte libre, il ne tient pas dans une colonne sans rendre la grille
 * illisible.
 *
 * Deux règles tenues par la sérialisation :
 *
 * 1. **Les identifiants stables sont préservés.** `docflow.id` est alloué par le
 *    serveur et porte l'identité du champ : le perdre détacherait les relations
 *    qui s'y accrochent et les positions du diagramme.
 * 2. **Les clés inconnues survivent.** Ce que cette grille n'affiche pas
 *    (`format`, `constraints`, relations…) est conservé tel quel — une surface
 *    d'édition ne doit jamais détruire ce qu'elle ne sait pas montrer.
 */

import { forwardRef, useCallback, useImperativeHandle, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentViewerHandle,
  ContentViewerProps,
} from '../../lib/contentSurfaces'
import type { TableSchema, TableSchemaField } from '../../lib/mld/adapter'

/** Vocabulaire logique servi par le codec (cf. article 5.8). */
const FIELD_TYPES = [
  'string', 'text', 'integer', 'number', 'boolean',
  'date', 'time', 'datetime', 'duration', 'uuid', 'object', 'array', 'any',
] as const

function safeParse(raw: string | null | undefined): TableSchema {
  if (!raw?.trim()) return {}
  try {
    return (parseYaml(raw) as TableSchema) ?? {}
  } catch {
    return {}
  }
}

function fieldsOf(schema: TableSchema): TableSchemaField[] {
  return Array.isArray(schema.fields) ? schema.fields : []
}

// ── Grille ────────────────────────────────────────────────────────────────────

interface GridProps {
  schema: TableSchema
  onChange?: (schema: TableSchema) => void
}

function FieldGrid({ schema, onChange }: GridProps) {
  const { t } = useTranslation()
  const fields = fieldsOf(schema)
  const readOnly = !onChange

  /** Modifie un champ SANS toucher à ses autres clés (`docflow.id` compris). */
  const patch = (index: number, change: Partial<TableSchemaField>) =>
    onChange?.({
      ...schema,
      fields: fields.map((f, i) => (i === index ? { ...f, ...change } : f)),
    })

  return (
    <table
      className="w-full min-w-[34rem] border-collapse text-sm"
      data-testid="field-grid"
    >
      <thead>
        <tr className="border-b border-gray-200 text-left text-xs text-gray-600">
          <th className="w-[30%] px-2 py-1 font-medium">{t('mld.fieldName')}</th>
          <th className="w-[22%] px-2 py-1 font-medium">{t('mld.fieldType')}</th>
          <th className="px-2 py-1 font-medium">{t('mld.fieldTitle')}</th>
          {!readOnly && <th className="w-8" />}
        </tr>
      </thead>
      <tbody>
        {fields.map((field, i) => (
          <tr key={field['docflow.id'] ?? i} data-testid={`field-row-${i}`} className="border-b border-gray-100">
            <td className="px-2 py-1">
              <input
                value={field.name ?? ''}
                readOnly={readOnly}
                aria-label={t('mld.fieldName')}
                onChange={(e) => patch(i, { name: e.target.value })}
                className="w-full bg-transparent font-mono outline-none"
              />
            </td>
            <td className="px-2 py-1">
              {readOnly ? (
                <span className="font-mono text-gray-600">{field.type}</span>
              ) : (
                <select
                  value={field.type ?? 'string'}
                  aria-label={t('mld.fieldType')}
                  onChange={(e) => patch(i, { type: e.target.value })}
                  className="w-full bg-transparent font-mono outline-none"
                >
                  {FIELD_TYPES.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              )}
            </td>
            <td className="px-2 py-1">
              <input
                value={field.title ?? ''}
                readOnly={readOnly}
                aria-label={t('mld.fieldTitle')}
                onChange={(e) => patch(i, { title: e.target.value })}
                className="w-full bg-transparent outline-none"
              />
            </td>
            {!readOnly && (
              <td className="px-1">
                <button
                  type="button"
                  aria-label={t('mld.removeField')}
                  data-testid={`field-remove-${i}`}
                  onClick={() => onChange?.({ ...schema, fields: fields.filter((_, j) => j !== i) })}
                  className="cursor-pointer border-0 bg-transparent px-1 text-gray-400 hover:text-red-600"
                >
                  ×
                </button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Surface ───────────────────────────────────────────────────────────────────

interface EntityViewProps {
  schema: TableSchema
  onChange?: (schema: TableSchema) => void
}

function EntityView({ schema, onChange }: EntityViewProps) {
  const { t } = useTranslation()
  const readOnly = !onChange

  return (
    <div className="flex flex-col gap-4 lg:flex-row" data-testid="table-schema-surface">
      {/* `min-w-0` laisserait la grille se réduire jusqu'à tronquer ses colonnes
          quand la place manque : on lui impose une largeur plancher, et c'est le
          conteneur qui défile horizontalement si nécessaire. */}
      <div className="min-w-0 flex-1 overflow-x-auto rounded border border-gray-200 bg-white">
        <FieldGrid schema={schema} onChange={onChange} />
        {!readOnly && (
          <button
            type="button"
            data-testid="field-add"
            onClick={() =>
              onChange?.({ ...schema, fields: [...fieldsOf(schema), { name: '', type: 'string' }] })
            }
            className="w-full cursor-pointer whitespace-nowrap border-0 border-t border-gray-200 bg-transparent px-2 py-1.5 text-left text-sm text-gray-600 hover:text-accent-700"
          >
            + {t('mld.addField')}
          </button>
        )}
      </div>

      {/* Panneau latéral : la description est du texte libre, elle ne tient pas
          dans une colonne de la grille sans la rendre illisible. */}
      <aside className="w-full shrink-0 lg:w-80" data-testid="description-panel">
        <label className="mb-1 block text-xs font-medium text-gray-600" htmlFor="entity-description">
          {t('mld.description')}
        </label>
        <textarea
          id="entity-description"
          value={schema.description ?? ''}
          readOnly={readOnly}
          onChange={(e) => onChange?.({ ...schema, description: e.target.value })}
          rows={8}
          className="w-full rounded border border-gray-200 bg-white p-2 text-sm outline-none"
        />
        <p className="mt-1 text-xs text-gray-500">{t('mld.descriptionHint')}</p>
      </aside>
    </div>
  )
}

export const TableSchemaEditor = forwardRef<ContentEditorHandle, ContentEditorProps>(
  ({ initialContent, onDirty }, ref) => {
    const parsed = useMemo(() => safeParse(initialContent), [initialContent])
    const [schema, setSchema] = useState<TableSchema | null>(null)

    useImperativeHandle(
      ref,
      () => ({
        // Rien n'a bougé → contenu d'origine intact : une sauvegarde ne doit pas
        // produire un diff gratuit (ni perdre les commentaires YAML de l'auteur
        // avant que la canonicalisation serveur ne s'en charge).
        getContent: async () => (schema ? stringifyYaml(schema) : initialContent),
      }),
      [schema, initialContent],
    )

    const handleChange = useCallback(
      (next: TableSchema) => {
        setSchema(next)
        onDirty()
      },
      [onDirty],
    )

    return <EntityView schema={schema ?? parsed} onChange={handleChange} />
  },
)
TableSchemaEditor.displayName = 'TableSchemaEditor'

export const TableSchemaViewer = forwardRef<ContentViewerHandle, ContentViewerProps>(
  ({ content }, ref) => {
    useImperativeHandle(ref, () => ({}), [])
    return <EntityView schema={safeParse(content)} />
  },
)
TableSchemaViewer.displayName = 'TableSchemaViewer'
