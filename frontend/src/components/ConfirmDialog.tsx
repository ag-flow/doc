import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { Button } from './ui/button'

interface Props {
  title: string
  /** Ce qui va se passer, en une phrase. */
  message: ReactNode
  /** Verbe explicite du bouton : « Supprimer le bloc », jamais « OK ». */
  confirmLabel: string
  /** Nombre d'éléments impactés — annoncé, jamais laissé à deviner. */
  impactCount?: number
  /** Phrase d'impact (accord et pluriel gérés par l'appelant si besoin). */
  impactMessage?: string
  destructive?: boolean
  pending?: boolean
  /** Confirmation verrouillée (ex. saisie de garde non conforme). */
  confirmDisabled?: boolean
  /** testId du bouton de confirmation (défaut : `<testId>-confirm`). */
  confirmTestId?: string
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
  testId?: string
}

/**
 * Confirmation d'une action destructive : élévation haute, verbe explicite,
 * impact annoncé. Échap annule ; le focus part sur le bouton d'annulation (et
 * non sur le bouton destructeur) et reste piégé dans le dialogue.
 */
export function ConfirmDialog({
  title, message, confirmLabel, impactCount, impactMessage,
  destructive = true, pending = false, confirmDisabled = false, error = null,
  onConfirm, onCancel, testId = 'confirm-dialog', confirmTestId,
}: Props) {
  const { t } = useTranslation()
  const cancelRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Le focus va sur « Annuler » : sur une action destructrice, la touche
    // Entrée réflexe ne doit pas déclencher la destruction.
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel()
        return
      }
      if (e.key !== 'Tab') return
      // Piège de focus : Tab tourne dans le dialogue au lieu de repartir dans la page.
      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusables || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      } else if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div className="dialog-backdrop z-50" data-testid={testId}>
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${testId}-title`}
      >
        <h4 className="dialog-title" id={`${testId}-title`}>{title}</h4>
        <div className="dialog-body">
          {typeof message === 'string' ? <p className="m-0">{message}</p> : message}
          {(impactMessage || impactCount !== undefined) && (
            <p className="m-0 mt-2 flex items-start gap-1.5 text-accent-2-700"
              data-testid={`${testId}-impact`}>
              <Warning size={15} weight="duotone" className="mt-0.5 shrink-0" />
              <span>{impactMessage ?? String(impactCount)}</span>
            </p>
          )}
        </div>

        <div aria-live="polite" className="empty:hidden">
          {error && <p className="field-error" data-testid={`${testId}-error`}>{error}</p>}
        </div>

        <div className="dialog-actions">
          <Button ref={cancelRef} variant="secondary" onClick={onCancel} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            disabled={pending || confirmDisabled}
            data-testid={confirmTestId ?? `${testId}-confirm`}
          >
            {pending ? t('common.loading') : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
