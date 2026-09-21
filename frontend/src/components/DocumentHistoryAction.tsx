/**
 * Action « historique de versions » — bouton + dialogue (épic MLD — F4e).
 *
 * Elle n'existait qu'en **édition**, par accident : rien ne la rendait
 * inapplicable à la lecture, elle avait simplement été ajoutée d'un côté et
 * oubliée de l'autre. C'est le symptôme que F4e attaque.
 *
 * Réunie ici, elle se monte dans les deux modes sans être écrite deux fois — et
 * la prochaine évolution profitera aux deux.
 *
 * Elle est en **lecture seule** sur le document : ni `expected_version`, ni
 * écriture. Rien ne s'oppose donc à l'offrir pendant l'édition.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ClockCounterClockwise } from '@phosphor-icons/react'
import { Button } from './ui/button'
import { VersionHistoryDialog } from './VersionHistoryDialog'

interface Props {
  ws: string
  docId: string
  currentVersion: number
}

export function DocumentHistoryAction({ ws, docId, currentVersion }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button
        variant="icon"
        size="sm"
        onClick={() => setOpen(true)}
        title={t('editor.history')}
        data-testid="document-history-btn"
      >
        <ClockCounterClockwise size={14} weight="duotone" />
      </Button>
      {open && (
        <VersionHistoryDialog
          ws={ws}
          docId={docId}
          currentVersion={currentVersion}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
