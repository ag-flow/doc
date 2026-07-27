import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useFieldState, type ValueType } from '../hooks/useFieldState'
import type { AllowedValueOut, PropertyValueOut } from '../lib/api'
import { Input } from './ui/input'
import { Button } from './ui/button'

interface PropertyFieldProps {
  ws: string
  docId: string
  prop: PropertyValueOut
  allowedValues: AllowedValueOut[]
  /** Rendu compact (sans label ni marge) pour l'édition inline en cellule de table. */
  compact?: boolean
  /** Appelé après chaque sauvegarde réussie (ex. rafraîchir/fermer la cellule). */
  onSaved?: () => void
}

function initialValue(prop: PropertyValueOut): string | null {
  return prop.type === 'restricted_list' ? prop.allowed_value_slug : prop.value
}

export function PropertyField({ ws, docId, prop, allowedValues, compact = false, onSaved }: PropertyFieldProps) {
  const { t } = useTranslation()
  const valueType: ValueType = prop.type as ValueType
  const { state, setValue, save, keepServer, keepMine } = useFieldState(
    initialValue(prop),
    prop.version,
    onSaved,
  )
  const wrapperClass = compact ? '' : 'mb-4'

  // Propriété gérée par le serveur (behavior auto_now / auto_now_create) :
  // lecture seule — le backend refuse de toute façon l'écriture manuelle.
  if (prop.behavior) {
    return (
      <div className={wrapperClass} data-testid={`property-${prop.prop_slug}`}>
        {!compact && (
          <label className="mb-1 flex items-center gap-1 text-sm font-medium text-gray-700">
            {prop.prop_label}
            <span
              className="ml-1 rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-gray-600"
              title={t('properties.autoHint')}
              data-testid={`property-auto-badge-${prop.prop_slug}`}
            >
              {t('properties.auto')}
            </span>
          </label>
        )}
        <p className="text-sm text-gray-700" data-testid={`property-input-${prop.prop_slug}`}>
          {prop.value ?? '—'}
        </p>
      </div>
    )
  }

  const commit = () => {
    if (state.status === 'dirty') void save(ws, docId, prop.prop_slug, valueType)
  }

  const fieldId = `prop-${prop.prop_slug}`
  const saving = state.status === 'saving'

  return (
    <div className={wrapperClass} data-testid={`property-${prop.prop_slug}`}>
      {!compact && (
        <label htmlFor={fieldId} className="mb-1 flex items-center gap-1 text-sm font-medium text-gray-700">
          {prop.prop_label}
          {prop.required && <span className="text-red-500">*</span>}
        </label>
      )}

      {prop.type === 'restricted_list' ? (
        /* Le select porte la valeur ; la couleur de la valeur choisie s'affiche
           en point discret À CÔTÉ — pas en pastille qui répéterait le libellé. */
        <div className="flex items-center gap-2">
          <select
            id={fieldId}
            className="input"
            value={state.value ?? ''}
            disabled={saving}
            onChange={(e) => {
              // Une liste fermée s'enregistre dès le choix (action délibérée et
              // discrète, comme le toggle bool ci-dessous) : on passe la valeur
              // explicitement pour ne pas dépendre d'un `state.value` encore périmé.
              const next = e.target.value || null
              setValue(next)
              void save(ws, docId, prop.prop_slug, valueType, next)
            }}
            data-testid={`property-input-${prop.prop_slug}`}
          >
            <option value="">{t('properties.none')}</option>
            {allowedValues.map((av) => (
              <option key={av.slug} value={av.slug}>
                {av.label}
              </option>
            ))}
          </select>
          {(() => {
            const av = state.value ? allowedValues.find((a) => a.slug === state.value) : null
            if (!av?.color) return null
            return (
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: av.color }}
                title={av.label}
                data-testid={`property-color-${prop.prop_slug}`}
              />
            )
          })()}
        </div>
      ) : prop.type === 'bool' ? (
        <label className="flex cursor-pointer items-center gap-2">
          <input
            id={fieldId}
            type="checkbox"
            className="h-4 w-4 rounded border-gray-300"
            checked={state.value === 'true'}
            disabled={saving}
            onChange={(e) => {
              // FE-05 : persister la valeur explicite du toggle, pas via `commit` qui
              // lirait un `state.status`/`state.value` encore périmés dans ce rendu.
              const next = e.target.checked ? 'true' : 'false'
              setValue(next)
              void save(ws, docId, prop.prop_slug, valueType, next)
            }}
            data-testid={`property-input-${prop.prop_slug}`}
          />
          <span className="text-sm text-gray-600">
            {state.value === 'true' ? t('common.yes', 'Oui') : t('common.no', 'Non')}
          </span>
        </label>
      ) : prop.type === 'date' ? (
        <Input
          id={fieldId}
          type="date"
          value={state.value ?? ''}
          disabled={saving}
          onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
          onBlur={commit}
          data-testid={`property-input-${prop.prop_slug}`}
        />
      ) : prop.type === 'url' ? (
        <div className="flex items-center gap-1">
          <Input
            id={fieldId}
            type="url"
            value={state.value ?? ''}
            disabled={saving}
            placeholder="https://..."
            onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
            onBlur={commit}
            data-testid={`property-input-${prop.prop_slug}`}
          />
          {state.value && (
            <a
              href={state.value}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 text-gray-400 hover:text-blue-600"
              tabIndex={-1}
            >
              <ExternalLink size={14} />
            </a>
          )}
        </div>
      ) : prop.type === 'float' ? (
        <Input
          id={fieldId}
          type="number"
          step="any"
          value={state.value ?? ''}
          disabled={saving}
          onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
          onBlur={commit}
          data-testid={`property-input-${prop.prop_slug}`}
        />
      ) : prop.type === 'reference' ? (
        <Input
          id={fieldId}
          type="text"
          placeholder="UUID du document cible"
          value={state.value ?? ''}
          disabled={saving}
          onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
          onBlur={commit}
          data-testid={`property-input-${prop.prop_slug}`}
          className="font-mono text-xs"
        />
      ) : (
        <Input
          id={fieldId}
          type={prop.type === 'int' ? 'number' : 'text'}
          value={state.value ?? ''}
          disabled={saving}
          onChange={(e) => setValue(e.target.value === '' ? null : e.target.value)}
          onBlur={commit}
          data-testid={`property-input-${prop.prop_slug}`}
        />
      )}

      {state.status === 'error' && (
        <p className="mt-1 text-xs text-red-600" data-testid={`property-error-${prop.prop_slug}`}>
          {state.errorMessage ?? t('error.generic')}
        </p>
      )}

      {state.status === 'conflict' && (
        <div
          className="mt-2 rounded border border-amber-300 bg-amber-50 p-2"
          data-testid={`property-conflict-${prop.prop_slug}`}
        >
          <p className="mb-2 text-xs text-amber-900">
            {t('properties.conflict.desc', {
              server: state.serverState?.value ?? state.serverState?.allowed_value_slug ?? '—',
            })}
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={keepServer}>
              {t('properties.conflict.keepServer')}
            </Button>
            <Button
              size="sm"
              onClick={() => void keepMine(ws, docId, prop.prop_slug, valueType)}
            >
              {t('properties.conflict.keepMine')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
