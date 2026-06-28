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
}

function initialValue(prop: PropertyValueOut): string | null {
  return prop.type === 'restricted_list' ? prop.allowed_value_slug : prop.value
}

export function PropertyField({ ws, docId, prop, allowedValues }: PropertyFieldProps) {
  const { t } = useTranslation()
  const valueType: ValueType = prop.type as ValueType
  const { state, setValue, save, keepServer, keepMine } = useFieldState(
    initialValue(prop),
    prop.version,
  )

  const commit = () => {
    if (state.status === 'dirty') void save(ws, docId, prop.prop_slug, valueType)
  }

  const fieldId = `prop-${prop.prop_slug}`
  const saving = state.status === 'saving'

  return (
    <div className="mb-4" data-testid={`property-${prop.prop_slug}`}>
      <label htmlFor={fieldId} className="mb-1 flex items-center gap-1 text-sm font-medium text-gray-700">
        {prop.prop_label}
        {prop.required && <span className="text-red-500">*</span>}
      </label>

      {prop.type === 'restricted_list' ? (
        <div className="flex flex-col gap-1">
          <select
            id={fieldId}
            className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
            value={state.value ?? ''}
            disabled={saving}
            onChange={(e) => {
              setValue(e.target.value || null)
            }}
            onBlur={commit}
            data-testid={`property-input-${prop.prop_slug}`}
          >
            <option value="">{t('properties.none')}</option>
            {allowedValues.map((av) => (
              <option key={av.slug} value={av.slug}>
                {av.label}
              </option>
            ))}
          </select>
          {state.value && (() => {
            const av = allowedValues.find((a) => a.slug === state.value)
            if (!av) return null
            return (
              <span
                className="inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium"
                style={
                  av.color
                    ? { backgroundColor: av.color, color: '#fff' }
                    : { backgroundColor: '#e5e7eb', color: '#374151' }
                }
                data-testid={`property-pill-${prop.prop_slug}`}
              >
                {av.label}
              </span>
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
              setValue(e.target.checked ? 'true' : 'false')
              setTimeout(commit, 0)
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
