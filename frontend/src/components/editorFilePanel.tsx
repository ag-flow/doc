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
import { useQuery } from '@tanstack/react-query'
import {
  EmbedTab,
  UploadTab,
  useBlockNoteEditor,
  useComponentsContext,
  useDictionary,
  type FilePanelProps,
} from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { artifactsApi, artifactTypesApi, ApiError, type ArtifactTypeOut } from '../lib/api'

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

/** Extension connue (présente dans le registre) terminant `name`, sinon ''. */
export function detectKnownExtension(name: string, known: readonly string[]): string {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return ''
  const ext = name.slice(dot + 1).toLowerCase()
  return known.includes(ext) ? ext : ''
}

/** Nom final : garantit que l'extension du type choisi termine bien le nom
 *  (évite un 422 « extension non autorisée » quand le nom n'en porte pas). */
export function finalFilename(name: string, ext: string): string {
  const trimmed = name.trim()
  if (!ext) return trimmed
  return trimmed.toLowerCase().endsWith(`.${ext}`) ? trimmed : `${trimmed}.${ext}`
}

/** Onglet « Coller » : zone Ctrl+V → nom + type → upload → bloc fichier. */
function PasteTab(
  props: FilePanelProps & { setLoading: (loading: boolean) => void; wsSlug: string },
) {
  const Components = useComponentsContext()!
  const { t } = useTranslation()
  const editor = useBlockNoteEditor()
  const [error, setError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [ext, setExt] = useState('')

  const { data: types = [] } = useQuery<ArtifactTypeOut[]>({
    queryKey: ['artifact-types'],
    queryFn: () => artifactTypesApi.list(),
    staleTime: 60_000,
  })
  const knownExts = types.map((ty) => ty.extension)

  const capture = useCallback(
    (picked: File) => {
      setError(null)
      setFile(picked)
      setName(picked.name)
      setExt(detectKnownExtension(picked.name, knownExts))
    },
    [knownExts],
  )

  const onPaste = useCallback(
    (e: ClipboardEvent<HTMLTextAreaElement>) => {
      e.preventDefault()
      const picked = fileFromClipboardData(e.clipboardData)
      if (!picked) {
        setError(t('artifact.pasteEmpty'))
        return
      }
      capture(picked)
    },
    [capture, t],
  )

  const onNameChange = (value: string) => {
    setName(value)
    const detected = detectKnownExtension(value, knownExts)
    if (detected) setExt(detected)
  }

  const insert = useCallback(() => {
    if (!file) return
    void (async () => {
      setError(null)
      props.setLoading(true)
      try {
        const mediaType = types.find((ty) => ty.extension === ext)?.media_type
        const created = await artifactsApi.upload(props.wsSlug, file, {
          filename: finalFilename(name, ext),
          mediaType,
        })
        editor.updateBlock(props.blockId, {
          props: { name: created.filename, url: created.url },
        } as never)
      } catch (e) {
        setError(e instanceof ApiError ? e.message : t('artifact.pasteError'))
      } finally {
        props.setLoading(false)
      }
    })()
  }, [editor, ext, file, name, props, t, types])

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
      {file && (
        <div className="artifact-paste-form" data-test="paste-form">
          <label className="artifact-paste-field">
            <span>{t('artifact.pasteName')}</span>
            <input
              className="input"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              data-test="paste-name"
            />
          </label>
          <label className="artifact-paste-field">
            <span>{t('artifact.pasteType')}</span>
            <select
              className="input"
              value={ext}
              onChange={(e) => setExt(e.target.value)}
              data-test="paste-type"
            >
              <option value="">{t('artifact.pasteTypeAuto')}</option>
              {types.map((ty) => (
                <option key={ty.extension} value={ty.extension}>
                  {ty.extension} — {ty.label || ty.media_type}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={insert}
            disabled={!name.trim()}
            data-test="paste-insert"
          >
            {t('artifact.pasteInsert')}
          </button>
        </div>
      )}
      {error && <div className="bn-error-text">{error}</div>}
    </Components.FilePanel.TabPanel>
  )
}

/** FilePanel custom passé à FilePanelController. */
export function EditorFilePanel(props: FilePanelProps & { wsSlug: string }) {
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
            tabPanel: (
              <PasteTab blockId={props.blockId} setLoading={setLoading} wsSlug={props.wsSlug} />
            ),
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
