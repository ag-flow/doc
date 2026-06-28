import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, type FunctionalTypeRich } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from './ui/button'
import { Input } from './ui/input'

interface Props {
  ws: string
  type: FunctionalTypeRich
}

export function TypePropertiesPanel({ ws, type }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [addingFor, setAddingFor] = useState<string | null>(null)
  const [templateValue, setTemplateValue] = useState(type.content_template ?? '')
  const [templateSaving, setTemplateSaving] = useState(false)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const [newLabel, setNewLabel] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [newColor, setNewColor] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

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
      setNewColor('')
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
    onSuccess: invalidate,
  })

  const restricted = type.properties.filter((p) => p.type === 'restricted_list')
  if (restricted.length === 0) return null

  function openAdd(propSlug: string) {
    setAddingFor(propSlug)
    setNewLabel('')
    setNewSlug('')
    setNewColor('')
    setSlugTouched(false)
    setFormError(null)
  }

  return (
    <div className="border-t border-gray-100 bg-gray-50 px-8 py-4 space-y-5">
      {restricted.map((prop) => (
        <div key={prop.slug}>
          <p className="mb-2 text-sm font-medium text-gray-700">
            {prop.label}{' '}
            <span className="font-mono text-xs text-gray-400">({prop.slug})</span>
            {prop.required && <span className="ml-1 text-red-500">*</span>}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {prop.allowed_values.map((av) => (
              <span
                key={av.slug}
                className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium"
                style={
                  av.color
                    ? { backgroundColor: av.color, color: '#fff' }
                    : { backgroundColor: '#e5e7eb', color: '#374151' }
                }
                data-testid={`val-pill-${prop.slug}-${av.slug}`}
              >
                {av.label}
                <button
                  className="ml-0.5 opacity-70 hover:opacity-100"
                  onClick={() =>
                    deleteMutation.mutate({ propSlug: prop.slug, valSlug: av.slug })
                  }
                  data-testid={`delete-val-${prop.slug}-${av.slug}`}
                  title={t('common.delete')}
                >
                  ×
                </button>
              </span>
            ))}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => openAdd(prop.slug)}
              data-testid={`add-val-${prop.slug}`}
            >
              + {t('types.addValue')}
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
                onChange={(e) => {
                  setSlugTouched(true)
                  setNewSlug(e.target.value)
                }}
                placeholder="slug"
                className="w-32 font-mono"
                data-testid="new-val-slug"
              />
              <input
                type="color"
                value={newColor || '#6366f1'}
                onChange={(e) => setNewColor(e.target.value)}
                className="h-9 w-10 cursor-pointer rounded border border-gray-300 p-0.5"
                data-testid="new-val-color"
                title={t('types.valueColor')}
              />
              <Button
                size="sm"
                disabled={!newLabel.trim() || !newSlug.trim() || createMutation.isPending}
                onClick={() =>
                  createMutation.mutate({
                    propSlug: prop.slug,
                    slug: newSlug.trim(),
                    label: newLabel.trim(),
                    color: newColor || null,
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
              {formError && <p className="text-xs text-red-600">{formError}</p>}
            </div>
          )}
        </div>
      ))}

      {/* Éditeur de template de contenu */}
      <div className="mt-6 rounded border border-gray-200 p-4">
        <h3 className="mb-2 text-sm font-semibold text-gray-700">
          {t('types.contentTemplate', 'Modèle de contenu')}
        </h3>
        <p className="mb-2 text-xs text-gray-500">
          {t('types.contentTemplateHint', 'Variables : {{title}}, {{date}} — appliqué à la création si le corps est vide.')}
        </p>
        <textarea
          className="block w-full rounded border border-gray-300 p-2 font-mono text-xs"
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
                void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })
              } catch (err) {
                setTemplateError(err instanceof Error ? err.message : String(err))
              } finally {
                setTemplateSaving(false)
              }
            }}
          >
            {t('types.saveTemplate', 'Enregistrer le modèle')}
          </Button>
          {templateError && <p className="text-xs text-red-600">{templateError}</p>}
        </div>
      </div>
    </div>
  )
}
