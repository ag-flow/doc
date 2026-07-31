/**
 * Panneau fichier custom de l'éditeur : reprend les onglets natifs de BlockNote
 * (Upload, Embed) et ajoute un onglet **Coller** qui lit le presse-papier,
 * en extrait une image/fichier et le téléverse comme un upload classique.
 *
 * S'appuie uniquement sur des points d'extension publics de BlockNote
 * (FilePanelController + tabs custom, UploadTab/EmbedTab réutilisés).
 */
import { useCallback, useState } from 'react'
import {
  EmbedTab,
  UploadTab,
  useBlockNoteEditor,
  useComponentsContext,
  useDictionary,
  type FilePanelProps,
} from '@blocknote/react'
import { useTranslation } from 'react-i18next'

/** Extrait un fichier image du presse-papier (première image trouvée), ou null.
 *  Exporté pour test — isolé de toute dépendance BlockNote. */
export async function readClipboardFile(
  clipboard: Clipboard | undefined = navigator.clipboard,
): Promise<File | null> {
  if (!clipboard?.read) return null
  const items = await clipboard.read()
  for (const item of items) {
    const type = item.types.find((ty) => ty.startsWith('image/'))
    if (type) {
      const blob = await item.getType(type)
      const ext = type.split('/')[1] || 'png'
      return new File([blob], `collage.${ext}`, { type })
    }
  }
  return null
}

/** Onglet « Coller » : presse-papier → upload → mise à jour du bloc fichier. */
function PasteTab(props: FilePanelProps & { setLoading: (loading: boolean) => void }) {
  const Components = useComponentsContext()!
  const { t } = useTranslation()
  const editor = useBlockNoteEditor()
  const [error, setError] = useState<string | null>(null)

  const paste = useCallback(() => {
    void (async () => {
      setError(null)
      props.setLoading(true)
      try {
        const file = await readClipboardFile()
        if (!file) {
          setError(t('artifact.pasteEmpty'))
          return
        }
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
  }, [editor, props, t])

  return (
    <Components.FilePanel.TabPanel className="bn-tab-panel">
      <Components.FilePanel.Button
        className="bn-button"
        onClick={paste}
        data-test="paste-clipboard"
      >
        {t('artifact.pasteButton')}
      </Components.FilePanel.Button>
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
