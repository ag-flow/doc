/**
 * Panneau fichier custom de l'éditeur : reprend les onglets natifs de BlockNote
 * (Upload, Embed) et ajoute un onglet **Coller**. Le collage se fait via une
 * zone qui capte l'événement `paste` (Ctrl+V) : contrairement à
 * navigator.clipboard.read() (limité aux images, HTTPS + permission), un
 * événement paste expose N'IMPORTE QUEL fichier copié — avec son vrai nom.
 *
 * S'appuie uniquement sur des points d'extension publics de BlockNote
 * (FilePanelController + tabs custom, UploadTab/EmbedTab réutilisés).
 */
import { useCallback, useState, type ClipboardEvent } from 'react'
import {
  EmbedTab,
  UploadTab,
  useBlockNoteEditor,
  useComponentsContext,
  useDictionary,
  type FilePanelProps,
} from '@blocknote/react'
import { useTranslation } from 'react-i18next'

/** Extrait le premier fichier d'un presse-papier d'événement paste (n'importe
 *  quel type : image copiée, fichier depuis l'explorateur…), ou null.
 *  Exporté pour test — isolé de toute dépendance BlockNote. */
export function fileFromClipboardData(dt: DataTransfer | null): File | null {
  if (!dt) return null
  if (dt.files && dt.files.length > 0) return dt.files[0]
  for (const item of dt.items) {
    if (item.kind === 'file') {
      const f = item.getAsFile()
      if (f) return f
    }
  }
  return null
}

/** Onglet « Coller » : zone Ctrl+V → upload → mise à jour du bloc fichier. */
function PasteTab(props: FilePanelProps & { setLoading: (loading: boolean) => void }) {
  const Components = useComponentsContext()!
  const { t } = useTranslation()
  const editor = useBlockNoteEditor()
  const [error, setError] = useState<string | null>(null)

  const onPaste = useCallback(
    (e: ClipboardEvent<HTMLTextAreaElement>) => {
      // Toujours neutraliser le collage natif : la zone ne doit jamais recevoir
      // de texte, seulement servir de cible au fichier.
      e.preventDefault()
      const file = fileFromClipboardData(e.clipboardData)
      if (!file) {
        setError(t('artifact.pasteEmpty'))
        return
      }
      void (async () => {
        setError(null)
        props.setLoading(true)
        try {
          if (editor.uploadFile !== undefined) {
            let updateData = await editor.uploadFile(file, props.blockId)
            if (typeof updateData === 'string') {
              updateData = { props: { name: file.name, url: updateData } }
            }
            editor.updateBlock(props.blockId, updateData as never)
          }
        } catch {
          setError(t('artifact.pasteError'))
        } finally {
          props.setLoading(false)
        }
      })()
    },
    [editor, props, t],
  )

  return (
    <Components.FilePanel.TabPanel className="bn-tab-panel">
      <textarea
        autoFocus
        onPaste={onPaste}
        onChange={() => undefined}
        value=""
        placeholder={t('artifact.pasteHint')}
        data-test="paste-zone"
        className="artifact-paste-zone"
      />
      {error && <div className="bn-error-text">{error}</div>}
    </Components.FilePanel.TabPanel>
  )
}

/** FilePanel custom passé à FilePanelController. */
export function EditorFilePanel(props: FilePanelProps) {
  const Components = useComponentsContext()!
  const dict = useDictionary()
  const { t } = useTranslation()
  const editor = useBlockNoteEditor()
  const [loading, setLoading] = useState(false)

  // L'onglet Coller (comme Upload) n'a de sens que si l'éditeur sait téléverser.
  const canUpload = editor.uploadFile !== undefined
  const tabs = [
    ...(canUpload
      ? [
          {
            name: dict.file_panel.upload.title,
            tabPanel: <UploadTab blockId={props.blockId} setLoading={setLoading} />,
          },
          {
            name: t('artifact.pasteTab'),
            tabPanel: <PasteTab blockId={props.blockId} setLoading={setLoading} />,
          },
        ]
      : []),
    {
      name: dict.file_panel.embed.title,
      tabPanel: <EmbedTab blockId={props.blockId} />,
    },
  ]
  const [openTab, setOpenTab] = useState(tabs[0].name)

  return (
    <Components.FilePanel.Root
      className="bn-panel"
      defaultOpenTab={openTab}
      openTab={openTab}
      setOpenTab={setOpenTab}
      tabs={tabs}
      loading={loading}
    />
  )
}
