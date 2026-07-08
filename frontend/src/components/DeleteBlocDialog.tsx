import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { ApiError, docsApi } from '../lib/api'
import { Button } from './ui/button'

interface DeleteBlocDialogProps {
  wsSlug: string
  blockSlug: string
  blockLabel: string
  onClose: () => void
  onDeleted: () => void
}

/** Confirmation de suppression d'un bloc en deux temps :
 *  1er « Supprimer » → tentative sans confirm ; si le bloc a des dépendants
 *  l'API répond 409 avec le décompte, qu'on affiche avant de reconfirmer la
 *  cascade. Bloc vide → suppression directe après la 1ʳᵉ confirmation. */
export function DeleteBlocDialog({
  wsSlug,
  blockSlug,
  blockLabel,
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      data-testid="delete-bloc-dialog"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">{t('blocs.deleteTitle')}</h2>

        {cascadeMsg ? (
          <div
            className="mb-4 flex gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
            data-testid="delete-bloc-cascade"
          >
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">{t('blocs.deleteWarnTitle')}</p>
              <p className="mt-1">{cascadeMsg}</p>
            </div>
          </div>
        ) : (
          <p className="mb-4 text-sm text-gray-600">
            {t('blocs.deleteConfirm', { label: blockLabel })}
          </p>
        )}

        {error && (
          <p className="mb-3 text-sm text-red-600" data-testid="delete-bloc-error">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={deleteMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <button
            type="button"
            onClick={() => deleteMutation.mutate(cascadeMsg !== null)}
            disabled={deleteMutation.isPending}
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white
                       transition-colors hover:bg-red-700 disabled:opacity-50"
            data-testid="delete-bloc-confirm"
          >
            {deleteMutation.isPending
              ? t('blocs.deleting')
              : cascadeMsg
                ? t('blocs.deleteConfirmCascade')
                : t('blocs.delete')}
          </button>
        </div>
      </div>
    </div>
  )
}
