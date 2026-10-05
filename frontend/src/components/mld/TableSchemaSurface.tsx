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

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentViewerHandle,
  ContentViewerProps,
} from '../../lib/contentSurfaces'
import type { TableSchema, TableSchemaField, TableSchemaRelation } from '../../lib/mld/adapter'
import type { EntityCandidate } from '../../lib/mld/candidates'
import { useEntityCandidates } from './useEntityCandidates'
import { MarkdownEditor } from '../MarkdownEditor'
import { MarkdownViewer } from '../MarkdownViewer'

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

const RELATIONS_KEY = 'docflow.relations' as const

/** Cardinalités servies par le codec, avec leur lecture en clair. */
const CARDINALITIES = [
  { value: 'many-to-one', hint: 'n → 1' },
  { value: 'one-to-many', hint: '1 → n' },
  { value: 'one-to-one', hint: '1 → 1' },
  { value: 'many-to-many', hint: 'n → n' },
] as const

function relationsOf(schema: TableSchema): TableSchemaRelation[] {
  const rels = schema[RELATIONS_KEY]
  return Array.isArray(rels) ? rels : []
}

function firstOf(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? ''
}

/**
 * Liste déroulante qui ne perd JAMAIS la valeur enregistrée.
 *
 * Une valeur absente des options — cible supprimée, champ renommé, relation
 * écrite avant que la liste n'existe — est ajoutée en fin de liste et signalée.
 * Sans cela, le simple affichage du formulaire réécrirait la relation avec la
 * première option venue : une surface d'édition ne détruit pas ce qu'elle ne
 * sait pas montrer.
 */
function PreservingSelect({
  value, options, onChange, label, placeholder, className, unknownSuffix,
}: {
  value: string
  options: { value: string; label: string; group?: string }[]
  onChange: (value: string) => void
  label: string
  placeholder: string
  className: string
  unknownSuffix: string
}) {
  const known = options.some((o) => o.value === value)
  const groups = useMemo(() => {
    const out = new Map<string, { value: string; label: string }[]>()
    for (const o of options) {
      const key = o.group ?? ''
      const list = out.get(key) ?? []
      list.push(o)
      out.set(key, list)
    }
    return [...out]
  }, [options])

  return (
    <select
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
      className={className}
    >
      <option value="">{placeholder}</option>
      {groups.map(([group, items]) =>
        group ? (
          <optgroup key={group} label={group}>
            {items.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </optgroup>
        ) : (
          items.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))
        ),
      )}
      {value !== '' && !known && (
        <option value={value}>{`${value} ${unknownSuffix}`}</option>
      )}
    </select>
  )
}

// ── Grille ────────────────────────────────────────────────────────────────────

interface GridProps {
  schema: TableSchema
  onChange?: (schema: TableSchema) => void
  /** Entités désignables par une relation. Passées en PROP : la grille ne va
   *  rien chercher elle-même, elle reste testable sans réseau. */
  candidates?: EntityCandidate[]
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
      className="w-full min-w-[34rem] border-collapse text-[17px]"
      data-testid="field-grid"
    >
      <thead>
        <tr className="border-b border-gray-200 text-left text-[13px] text-gray-600">
          {/* Le nom est un identifiant technique, souvent long (`libelle_article`) :
              il lui faut de quoi se lire sans troncature. */}
          <th className="w-[calc(30%+3cm)] px-2 py-1 font-medium">{t('mld.fieldName')}</th>
          <th className="w-[9rem] px-2 py-1 font-medium">{t('mld.fieldType')}</th>
          {/* Sans largeur : le libellé prend tout ce qui reste, jusqu'au bord. */}
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

// ── Relations ─────────────────────────────────────────────────────────────────

/**
 * Édition des relations sortantes de l'entité.
 *
 * Sans elle, une relation n'était plus modifiable nulle part : la grille avait
 * remplacé la vue YAML brute, qui était jusque-là le seul moyen d'y toucher.
 *
 * `docflow.id` n'est jamais exposé ni touché — c'est lui qui rattache les coudes
 * persistés du diagramme à la relation.
 */
function RelationGrid({ schema, onChange, candidates = [] }: GridProps) {
  const { t } = useTranslation()
  const relations = relationsOf(schema)
  const readOnly = !onChange

  /** Entités désignables, groupées par chemin. Le modèle courant n'est pas
   *  étiqueté « autre part » : c'est le cas nominal, il vient en tête. */
  const targetOptions = useMemo(
    () =>
      candidates.map((c) => ({
        value: c.name,
        label: c.title,
        group: c.sameModel ? t('mld.relationTargetThisModel') : c.path.join(' / ') || '—',
      })),
    [candidates, t],
  )

  /** Champs de CETTE entité — l'extrémité de départ. */
  const ownFieldOptions = useMemo(
    () => fieldsOf(schema).filter((f) => f.name).map((f) => ({
      value: f.name as string,
      label: f.title ? `${f.name} · ${f.title}` : (f.name as string),
    })),
    [schema],
  )

  /** Champs de la cible choisie — vide tant qu'elle n'est pas résolue. */
  const targetFieldOptions = (resource: string) => {
    const found = candidates.find((c) => c.name === resource)
    return (found?.fields ?? []).map((f) => ({
      value: f.name,
      label: f.title ? `${f.name} · ${f.title}` : f.name,
    }))
  }

  const patch = (index: number, change: Partial<TableSchemaRelation>) =>
    onChange?.({
      ...schema,
      [RELATIONS_KEY]: relations.map((r, i) => (i === index ? { ...r, ...change } : r)),
    })

  if (readOnly && relations.length === 0) return null

  return (
    <div className="mt-4 rounded border border-gray-200 bg-white" data-testid="relation-grid">
      <div className="border-b border-gray-200 px-2 py-1.5 text-[13px] font-medium text-gray-600">
        {t('mld.relations')}
      </div>

      {relations.map((rel, i) => (
        <div
          key={rel['docflow.id'] ?? i}
          data-testid={`relation-row-${i}`}
          className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-2 py-1.5 text-[17px]"
        >
          <input
            value={rel.name ?? ''}
            readOnly={readOnly}
            aria-label={t('mld.relationName')}
            placeholder={t('mld.relationName')}
            onChange={(e) => patch(i, { name: e.target.value })}
            className="w-44 bg-transparent font-mono outline-none"
          />
          <select
            value={rel.cardinality ?? 'many-to-one'}
            disabled={readOnly}
            aria-label={t('mld.relationCardinality')}
            onChange={(e) => patch(i, { cardinality: e.target.value })}
            className="bg-transparent font-mono outline-none"
          >
            {CARDINALITIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.hint}
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-500">{t('mld.relationFrom')}</span>
          {readOnly ? (
            <span className="w-28 font-mono">{firstOf(rel.from)}</span>
          ) : (
            <PreservingSelect
              value={firstOf(rel.from)}
              options={ownFieldOptions}
              onChange={(v) => patch(i, { from: v })}
              label={t('mld.relationFrom')}
              placeholder={t('mld.relationFrom')}
              unknownSuffix={t('mld.unknownValue')}
              className="w-36 bg-transparent font-mono outline-none"
            />
          )}
          <span className="text-xs text-gray-500">→</span>
          {readOnly ? (
            <span className="w-28 font-mono">{rel.to?.resource ?? ''}</span>
          ) : (
            <PreservingSelect
              value={rel.to?.resource ?? ''}
              options={targetOptions}
              // Changer de cible périme le champ visé : le garder pointerait
              // vers un champ d'une AUTRE entité, silencieusement.
              onChange={(v) => patch(i, { to: { resource: v, fields: '' } })}
              label={t('mld.relationTarget')}
              placeholder={t('mld.relationTarget')}
              unknownSuffix={t('mld.unknownValue')}
              className="w-48 bg-transparent font-mono outline-none"
            />
          )}
          {readOnly ? (
            <span className="w-24 font-mono">{firstOf(rel.to?.fields)}</span>
          ) : (
            <PreservingSelect
              value={firstOf(rel.to?.fields)}
              options={targetFieldOptions(rel.to?.resource ?? '')}
              onChange={(v) => patch(i, { to: { ...rel.to, fields: v } })}
              label={t('mld.relationTargetField')}
              placeholder={t('mld.relationTargetField')}
              unknownSuffix={t('mld.unknownValue')}
              className="w-36 bg-transparent font-mono outline-none"
            />
          )}
          {!readOnly && (
            <button
              type="button"
              aria-label={t('mld.removeRelation')}
              data-testid={`relation-remove-${i}`}
              onClick={() =>
                onChange?.({
                  ...schema,
                  [RELATIONS_KEY]: relations.filter((_, j) => j !== i),
                })
              }
              className="ml-auto cursor-pointer border-0 bg-transparent px-1 text-gray-400 hover:text-red-600"
            >
              ×
            </button>
          )}
        </div>
      ))}

      {!readOnly && (
        <button
          type="button"
          data-testid="relation-add"
          onClick={() =>
            onChange?.({
              ...schema,
              [RELATIONS_KEY]: [
                ...relations,
                { name: '', cardinality: 'many-to-one', from: '', to: { resource: '', fields: '' } },
              ],
            })
          }
          className="w-full cursor-pointer whitespace-nowrap border-0 bg-transparent px-2 py-1.5 text-left text-sm text-gray-600 hover:text-accent-700"
        >
          + {t('mld.addRelation')}
        </button>
      )}
    </div>
  )
}

// ── Surface ───────────────────────────────────────────────────────────────────

interface EntityViewProps {
  schema: TableSchema
  onChange?: (schema: TableSchema) => void
  candidates?: EntityCandidate[]
  /** Rédaction de la description — l'éditeur markdown complet, monté par
   *  l'appelant qui en tient la référence pour la sauvegarde. */
  description?: ReactNode
}

function EntityView({ schema, onChange, candidates, description }: EntityViewProps) {
  const { t } = useTranslation()
  const readOnly = !onChange

  return (
    <div className="flex flex-col gap-4 lg:flex-row" data-testid="table-schema-surface">
      {/* Part égale : la grille a peu de colonnes et n'a pas besoin de plus,
          tandis que la description est de la prose — c'est elle qu'on écrit au
          long, et c'est par elle qu'on retrouve une entité dans la recherche.
          `min-w-0` seul laissait la grille se réduire jusqu'à tronquer ses
          colonnes ; le conteneur défile si la place manque vraiment. */}
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
        <RelationGrid schema={schema} onChange={onChange} candidates={candidates} />
      </div>

      {/* Panneau latéral : la description est du texte libre, elle ne tient pas
          dans une colonne de la grille sans la rendre illisible. */}
      <aside className="w-full min-w-0 lg:flex-1" data-testid="description-panel">
        <div className="mb-1 text-xs font-medium text-gray-600">{t('mld.description')}</div>
        {description}
        <p className="mt-1 text-xs text-gray-500">{t('mld.descriptionHint')}</p>
      </aside>
    </div>
  )
}

export const TableSchemaEditor = forwardRef<ContentEditorHandle, ContentEditorProps>(
  ({ initialContent, onDirty, wsSlug, docId }, ref) => {
    const parsed = useMemo(() => safeParse(initialContent), [initialContent])
    const candidates = useEntityCandidates(docId)
    const [schema, setSchema] = useState<TableSchema | null>(null)
    // La description est rédigée dans l'éditeur markdown complet, qui est NON
    // CONTRÔLÉ : on ne la lit qu'au moment de la sauvegarde, par sa référence.
    const descriptionRef = useRef<ContentEditorHandle>(null)
    const [descriptionTouched, setDescriptionTouched] = useState(false)

    useImperativeHandle(
      ref,
      () => ({
        getContent: async () => {
          // Rien n'a bougé → contenu d'origine intact : une sauvegarde ne doit
          // pas produire un diff gratuit (ni perdre les commentaires YAML de
          // l'auteur avant que la canonicalisation serveur ne s'en charge).
          if (!schema && !descriptionTouched) return initialContent

          const next: TableSchema = { ...(schema ?? parsed) }
          const written = (await descriptionRef.current?.getContent())?.trim()
          if (written) next.description = written
          else delete next.description
          return stringifyYaml(next)
        },
      }),
      [schema, descriptionTouched, parsed, initialContent],
    )

    const handleChange = useCallback(
      (next: TableSchema) => {
        setSchema(next)
        onDirty()
      },
      [onDirty],
    )

    const handleDescriptionDirty = useCallback(() => {
      setDescriptionTouched(true)
      onDirty()
    }, [onDirty])

    return (
      <EntityView
        schema={schema ?? parsed}
        onChange={handleChange}
        candidates={candidates}
        description={
          <MarkdownEditor
            ref={descriptionRef}
            initialContent={parsed.description ?? ''}
            onDirty={handleDescriptionDirty}
            wsSlug={wsSlug}
          />
        }
      />
    )
  },
)
TableSchemaEditor.displayName = 'TableSchemaEditor'

export const TableSchemaViewer = forwardRef<ContentViewerHandle, ContentViewerProps>(
  ({ content }, ref) => {
    const schema = useMemo(() => safeParse(content), [content])
    useImperativeHandle(ref, () => ({}), [])

    return (
      <EntityView
        schema={schema}
        description={
          schema.description ? <MarkdownViewer content={schema.description} bare /> : null
        }
      />
    )
  },
)
TableSchemaViewer.displayName = 'TableSchemaViewer'
