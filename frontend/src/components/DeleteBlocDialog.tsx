import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { ApiError, docsApi } from '../lib/api'
import { Button } from './ui/button'

interface DeleteBlocDialogProps {
  wsSlug: string
  blockSlug: string
  blockLabel: string
  /** Volumétrie annoncée d'entrée : on ne demande pas de confirmer à l'aveugle. */
  documentsCount: number
  onClose: () => void
  onDeleted: () => void
}

/** Confirmation de suppression d'un bloc en deux temps :
 *  1er « Supprimer » → tentative sans confirm ; si le bloc a des dépendants
 *  l'API répond 409 avec le décompte complet (documents ET blocs enfants),
 *  qu'on affiche avant de reconfirmer la cascade. Bloc vide → suppression
 *  directe après la 1ʳᵉ confirmation. */
export function DeleteBlocDialog({
  wsSlug,
  blockSlug,
  blockLabel,
  documentsCount,
  onClose,
  onDeleted,
}: DeleteBlocDialogProps) {
  const { t } = useTranslation()
  const [cascadeMsg, setCascadeMsg] = useState<string | null>(null)
  const [error, setError] = useState('')

  const deleteMutation = useMutation({
    mutationFn: (confirm: boolean) => docsApi.deleteBlock(wsSlug, blockSlug, confirm),
    onSuccess: () => onDeleted(),
    onError: (e: Error) => {
      // 409 = dépendants : on bascule en confirmation de cascade avec le décompte.
      if (e instanceof ApiError && e.status === 409) {
        setCascadeMsg(e.message)
      } else {
        setError(e instanceof Error ? e.message : t('error.generic'))
      }
    },
  })

  return (
    <div className="dialog-backdrop z-50" data-testid="delete-bloc-dialog">
      <div className="dialog">
        <h4 className="dialog-title">{t('blocs.deleteTitle')}</h4>

        {cascadeMsg ? (
          <div className="dialog-body flex gap-2 text-accent-2-700" data-testid="delete-bloc-cascade">
            <Warning size={16} weight="duotone" className="mt-0.5 shrink-0" />
            <div>
              <p className="m-0 [font-family:var(--font-heading)] font-[600]">
                {t('blocs.deleteWarnTitle')}
              </p>
              <p className="m-0 mt-1">{cascadeMsg}</p>
            </div>
          </div>
        ) : (
          <div className="dialog-body">
            <p className="m-0">{t('blocs.deleteConfirm', { label: blockLabel })}</p>
            <p className="m-0 mt-2" data-testid="delete-bloc-count">
              {documentsCount === 0
                ? t('blocs.deleteEmptyHint')
                : t('blocs.deleteDocsCount', { count: documentsCount })}
            </p>
          </div>
        )}

        <div aria-live="polite">
          {error && (
            <p className="field-error" data-testid="delete-bloc-error">{error}</p>
          )}
        </div>

        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose} disabled={deleteMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteMutation.mutate(cascadeMsg !== null)}
            disabled={deleteMutation.isPending}
            data-testid="delete-bloc-confirm"
          >
            {deleteMutation.isPending
              ? t('blocs.deleting')
              : cascadeMsg
                ? t('blocs.deleteConfirmCascade')
                : t('blocs.delete')}
          </Button>
        </div>
      </div>
    </div>
  )
}
