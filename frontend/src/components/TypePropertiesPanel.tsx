import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, X } from '@phosphor-icons/react'
import { api, type FunctionalTypeRich } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Field } from './ui/field'
import { ConfirmDialog } from './ConfirmDialog'

interface Props {
  ws: string
  type: FunctionalTypeRich
  onClose: () => void
}

/** Couleurs de valeur prises dans le système — pas d'arc-en-ciel. Le neutre est
 *  le défaut ; le cyan gradue l'avancement ; le magenta est réservé à l'état
 *  d'échec ou final. */
const VALUE_COLORS: { value: string | null; labelKey: string; swatch: string }[] = [
  { value: null, labelKey: 'types.colorNone', swatch: 'var(--color-neutral-300)' },
  { value: '#99e0ff', labelKey: 'accent-300', swatch: '#99e0ff' },
  { value: '#0088b0', labelKey: 'accent', swatch: '#0088b0' },
  { value: '#006786', labelKey: 'accent-700', swatch: '#006786' },
  { value: '#d6006c', labelKey: 'accent-2', swatch: '#d6006c' },
]

const SCALAR_TYPES = ['text', 'int', 'float', 'date', 'bool', 'url', 'restricted_list'] as const

/** Chip d'une valeur autorisée : teintes du système ; une couleur héritée d'un
 *  ancien choix libre reste affichée telle quelle (aucune migration de données). */
function ValueChip({ label, color, onDelete, testId, deleteTestId, deleteTitle }: {
  label: string
  color: string | null
  onDelete: () => void
  testId: string
  deleteTestId: string
  deleteTitle: string
}) {
  const style = color
    ? { backgroundColor: color, color: color === '#99e0ff' ? 'var(--color-ink)' : 'var(--color-paper)' }
    : undefined
  return (
    <span className={`tag ${color ? '' : 'tag-neutral'} gap-1`} style={style} data-testid={testId}>
      {label}
      <button
        type="button"
        className="border-0 bg-transparent p-0 text-inherit opacity-70 hover:opacity-100"
        onClick={onDelete}
        data-testid={deleteTestId}
        title={deleteTitle}
        aria-label={`${deleteTitle} ${label}`}
      >
        <X size={11} weight="bold" />
      </button>
    </span>
  )
}

/**
 * Édition en place d'un type : valeurs des listes restreintes, ajout de
 * propriété, modèle de contenu. S'ouvre sous la ligne du type — pas de modale.
 */
export function TypePropertiesPanel({ ws, type, onClose }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [addingFor, setAddingFor] = useState<string | null>(null)
  const [templateValue, setTemplateValue] = useState(type.content_template ?? '')
  const [templateSaving, setTemplateSaving] = useState(false)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const [newLabel, setNewLabel] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [newColor, setNewColor] = useState<string | null>(null)
  const [slugTouched, setSlugTouched] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteVal, setDeleteVal] = useState<{ propSlug: string; slug: string; label: string } | null>(null)
  const [deleteValError, setDeleteValError] = useState<string | null>(null)

  // Ajout de propriété (libellé, type scalaire, obligatoire).
  const [addingProp, setAddingProp] = useState(false)
  const [propLabel, setPropLabel] = useState('')
  const [propSlug, setPropSlug] = useState('')
  const [propType, setPropType] = useState<string>('text')
  const [propRequired, setPropRequired] = useState(false)
  const [propSlugTouched, setPropSlugTouched] = useState(false)
  const [propError, setPropError] = useState<string | null>(null)

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })

  const createMutation = useMutation({
    mutationFn: (vars: {
      propSlug: string
      slug: string
      label: string
      color: string | null
      position: number
    }) =>
      api.post(
        `/workspaces/${ws}/types/${type.slug}/properties/${vars.propSlug}/values`,
        { slug: vars.slug, label: vars.label, position: vars.position, color: vars.color },
      ),
    onSuccess: () => {
      invalidate()
      setAddingFor(null)
      setNewLabel('')
      setNewSlug('')
      setNewColor(null)
      setSlugTouched(false)
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (vars: { propSlug: string; valSlug: string }) =>
      api.delete(
        `/workspaces/${ws}/types/${type.slug}/properties/${vars.propSlug}/values/${vars.valSlug}`,
      ),
    onSuccess: () => {
      invalidate()
      setDeleteVal(null)
      setDeleteValError(null)
    },
    // 409 = valeur utilisée : le message de l'API porte le décompte.
    onError: (err: Error) => setDeleteValError(err.message),
  })

  const createPropMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${ws}/types/${type.slug}/properties`, {
        slug: propSlug.trim(),
        label: propLabel.trim(),
        type: propType,
        required: propRequired,
      }),
    onSuccess: () => {
      invalidate()
      setAddingProp(false)
      setPropLabel('')
      setPropSlug('')
      setPropType('text')
      setPropRequired(false)
      setPropSlugTouched(false)
      setPropError(null)
    },
    onError: (err: Error) => setPropError(err.message),
  })

  const restricted = (type.properties ?? []).filter((p) => p.type === 'restricted_list')

  function openAdd(slug: string) {
    setAddingFor(slug)
    setNewLabel('')
    setNewSlug('')
    setNewColor(null)
    setSlugTouched(false)
    setFormError(null)
  }

  return (
    <div className="space-y-5 border-b border-[var(--color-divider)] bg-surface px-8 py-4">
      <div className="flex items-start justify-between">
        <h6 className="m-0 text-ink/[0.5]">{type.label}</h6>
        <Button variant="icon" size="sm" onClick={onClose} title={t('types.close')}
          aria-label={t('types.close')} data-testid={`close-panel-${type.slug}`}>
          <X size={14} weight="bold" />
        </Button>
      </div>

      {restricted.map((prop) => (
        <div key={prop.slug}>
          <p className="mb-2 text-[14px] font-[600] [font-family:var(--font-heading)]">
            {prop.label}{' '}
            <span className="text-[11px] font-normal text-accent-700 [font-family:var(--font-mono)]">
              {prop.slug}
            </span>
            {prop.required && <span className="ml-1 text-accent-2-700">*</span>}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {prop.allowed_values.map((av) => (
              <ValueChip
                key={av.slug}
                label={av.label}
                color={av.color}
                onDelete={() => {
                  setDeleteVal({ propSlug: prop.slug, slug: av.slug, label: av.label })
                  setDeleteValError(null)
                }}
                testId={`val-pill-${prop.slug}-${av.slug}`}
                deleteTestId={`delete-val-${prop.slug}-${av.slug}`}
                deleteTitle={t('common.delete')}
              />
            ))}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => openAdd(prop.slug)}
              data-testid={`add-val-${prop.slug}`}
            >
              <Plus size={12} weight="duotone" /> {t('types.addValue')}
            </Button>
          </div>

          {addingFor === prop.slug && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Input
                value={newLabel}
                onChange={(e) => {
                  setNewLabel(e.target.value)
                  if (!slugTouched) setNewSlug(labelToSlug(e.target.value))
                }}
                placeholder={t('types.valueLabel')}
                className="w-40"
                autoFocus
                data-testid="new-val-label"
              />
              <Input
                value={newSlug}
                onChange={(e) => { setSlugTouched(true); setNewSlug(e.target.value) }}
                placeholder="slug"
                className="w-32 [font-family:var(--font-mono)]"
                data-testid="new-val-slug"
              />
              {/* Couleur : nuancier du système, pas de pipette libre. */}
              <span className="flex items-center gap-1" role="radiogroup"
                aria-label={t('types.valueColor')} data-testid="new-val-color">
                {VALUE_COLORS.map((c) => (
                  <button
                    key={c.value ?? 'none'}
                    type="button"
                    role="radio"
                    aria-checked={newColor === c.value}
                    title={c.value ?? t('types.colorNone')}
                    onClick={() => setNewColor(c.value)}
                    className={`h-6 w-6 rounded-full border-2 ${
                      newColor === c.value ? 'border-ink' : 'border-transparent'
                    }`}
                    style={{ backgroundColor: c.swatch }}
                    data-testid={`color-${c.value ?? 'none'}`}
                  />
                ))}
              </span>
              <Button
                size="sm"
                disabled={!newLabel.trim() || !newSlug.trim() || createMutation.isPending}
                onClick={() =>
                  createMutation.mutate({
                    propSlug: prop.slug,
                    slug: newSlug.trim(),
                    label: newLabel.trim(),
                    color: newColor,
                    position: prop.allowed_values.length,
                  })
                }
                data-testid="confirm-add-val"
              >
                {t('types.save')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setAddingFor(null)}>
                {t('types.cancel')}
              </Button>
              {formError && <p className="field-error m-0">{formError}</p>}
            </div>
          )}
        </div>
      ))}

      {/* ── Ajout de propriété ── */}
      <div>
        {!addingProp ? (
          <Button variant="ghost" size="sm" onClick={() => setAddingProp(true)}
            data-testid={`add-prop-${type.slug}`}>
            <Plus size={12} weight="duotone" /> {t('types.addProperty')}
          </Button>
        ) : (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (propLabel.trim() && propSlug.trim()) createPropMutation.mutate()
            }}
            data-testid={`add-prop-form-${type.slug}`}
          >
            <Field label={t('types.propLabel')} htmlFor={`prop-label-${type.slug}`}>
              <Input
                id={`prop-label-${type.slug}`}
                value={propLabel}
                onChange={(e) => {
                  setPropLabel(e.target.value)
                  if (!propSlugTouched) setPropSlug(labelToSlug(e.target.value))
                }}
                className="w-40"
                autoFocus
              />
            </Field>
            <Field label={t('types.slug')} htmlFor={`prop-slug-${type.slug}`}>
              <Input
                id={`prop-slug-${type.slug}`}
                value={propSlug}
                onChange={(e) => { setPropSlugTouched(true); setPropSlug(e.target.value) }}
                className="w-32 [font-family:var(--font-mono)]"
              />
            </Field>
            <Field label={t('types.propType')} htmlFor={`prop-type-${type.slug}`}>
              <select
                id={`prop-type-${type.slug}`}
                className="input w-auto"
                value={propType}
                onChange={(e) => setPropType(e.target.value)}
                data-testid={`prop-type-select-${type.slug}`}
              >
                {SCALAR_TYPES.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
              </select>
            </Field>
            <label className="mb-2 flex items-center gap-1.5 text-[14px]">
              <input
                type="checkbox"
                checked={propRequired}
                onChange={(e) => setPropRequired(e.target.checked)}
                data-testid={`prop-required-${type.slug}`}
              />
              {t('types.propRequired')}
            </label>
            <Button type="submit" size="sm"
              disabled={!propLabel.trim() || !propSlug.trim() || createPropMutation.isPending}
              data-testid={`confirm-add-prop-${type.slug}`}>
              {t('types.save')}
            </Button>
            <Button type="button" size="sm" variant="secondary"
              onClick={() => { setAddingProp(false); setPropError(null) }}>
              {t('types.cancel')}
            </Button>
            {/* DoD : une propriété obligatoire rend incomplets les documents
                existants du type — annoncé AVANT l'enregistrement. */}
            {propRequired && type.documents_count > 0 && (
              <p className="m-0 w-full text-[12px] text-accent-2-700"
                data-testid={`required-warn-${type.slug}`} role="alert">
                {t('types.requiredWarn', { count: type.documents_count })}
              </p>
            )}
            {propError && <p className="field-error m-0 w-full">{propError}</p>}
          </form>
        )}
      </div>

      {/* ── Modèle de contenu ── */}
      <div>
        <h6 className="mb-1 text-ink/[0.5]">{t('types.contentTemplate', 'Modèle de contenu')}</h6>
        <p className="mb-2 text-[12px] text-ink/[0.55]">
          {t('types.contentTemplateHint', {
            defaultValue: 'Variables : {{title}}, {{date}} — appliqué à la création si le corps est vide.',
            interpolation: { skipOnVariables: true },
          })}
        </p>
        <textarea
          className="input [font-family:var(--font-mono)] text-[12px]"
          rows={6}
          value={templateValue}
          onChange={(e) => setTemplateValue(e.target.value)}
          placeholder="# {{title}}&#10;> Créé le {{date}}&#10;&#10;## Contexte"
          data-testid={`template-editor-${type.slug}`}
        />
        <div className="mt-2 flex items-center gap-2">
          <Button
            size="sm"
            disabled={templateSaving}
            onClick={async () => {
              setTemplateSaving(true)
              setTemplateError(null)
              try {
                await api.patch(`/workspaces/${ws}/types/${type.slug}`, {
                  content_template: templateValue || null,
                })
                invalidate()
              } catch (err) {
                setTemplateError(err instanceof Error ? err.message : String(err))
              } finally {
                setTemplateSaving(false)
              }
            }}
          >
            {t('types.saveTemplate', 'Enregistrer le modèle')}
          </Button>
          {templateError && <p className="field-error m-0">{templateError}</p>}
        </div>
      </div>

      {deleteVal && (
        <ConfirmDialog
          testId="delete-val-dialog"
          title={t('types.deleteValueTitle')}
          message={t('types.deleteValueMsg', { label: deleteVal.label, prop: deleteVal.propSlug })}
          confirmLabel={t('types.deleteValue')}
          pending={deleteMutation.isPending}
          error={deleteValError}
          onConfirm={() =>
            deleteMutation.mutate({ propSlug: deleteVal.propSlug, valSlug: deleteVal.slug })
          }
          onCancel={() => { setDeleteVal(null); setDeleteValError(null) }}
        />
      )}
    </div>
  )
}
