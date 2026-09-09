import { createReactBlockSpec } from '@blocknote/react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import {
  ArrowSquareOut,
  ArrowsOut,
  DownloadSimple,
  File as FileIcon,
  FileArchive,
  FileAudio,
  FileCsv,
  FileDoc,
  FileImage,
  FilePdf,
  FilePpt,
  FileText,
  FileVideo,
  FileXls,
  type Icon,
} from '@phosphor-icons/react'
import { artifactsApi, type ArtifactMetaOut } from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { humanFileSize } from '../lib/fileSize'
import { FullscreenOverlay } from './FullscreenView'

/** Icône représentative selon le media type / l'extension. */
function iconFor(mediaType: string, extension: string): Icon {
  if (mediaType.startsWith('image/')) return FileImage
  if (mediaType.startsWith('audio/')) return FileAudio
  if (mediaType.startsWith('video/')) return FileVideo
  if (mediaType === 'application/pdf') return FilePdf
  if (mediaType === 'text/csv') return FileCsv
  if (mediaType.startsWith('text/') || mediaType === 'application/json') return FileText
  if (extension === 'zip') return FileArchive
  if (extension === 'docx') return FileDoc
  if (extension === 'xlsx') return FileXls
  if (extension === 'pptx') return FilePpt
  return FileIcon
}

/** Déclenche le téléchargement d'un blob sous un nom de fichier donné. */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Vue de la puce artefact (exportée pour les tests) : icône, nom, type,
 *  taille, plus Télécharger (blob authentifié) et Ouvrir (lien signé). */
export function ArtifactChipView({ id, label }: { id: string; label: string }) {
  const { currentSlug: ws } = useWorkspace()
  const meta = useQuery<ArtifactMetaOut>({
    queryKey: ['artifact-meta', ws, id],
    queryFn: () => artifactsApi.getMeta(ws!, id),
    enabled: Boolean(ws && id),
    staleTime: 60_000,
  })

  const name = label || meta.data?.filename || id
  const Glyph = meta.data ? iconFor(meta.data.media_type, meta.data.extension) : FileIcon
  const isImage = Boolean(meta.data?.media_type.startsWith('image/'))
  const [fullUrl, setFullUrl] = useState<string | null>(null)

  async function download() {
    if (!ws || !meta.data) return
    const blob = await artifactsApi.getBlob(ws, id, true)
    triggerDownload(blob, meta.data.filename)
  }

  async function open() {
    if (!ws) return
    const link = await artifactsApi.getLink(ws, id)
    window.open(link.url, '_blank', 'noopener')
  }

  // Plein écran d'une image : on affiche le contenu via le lien signé, comme
  // « Ouvrir », mais dans l'overlay de rendu commun plutôt qu'un nouvel onglet.
  async function openFullscreen() {
    if (!ws) return
    const link = await artifactsApi.getLink(ws, id)
    setFullUrl(link.url)
  }

  return (
    <div className="artifact-chip" data-testid="artifact-chip" data-artifact-id={id}>
      <Glyph size={30} weight="duotone" className="artifact-chip-icon" />
      <div className="artifact-chip-body">
        <span className="artifact-chip-name" title={name}>
          {name}
        </span>
        <span className="artifact-chip-meta">
          {meta.isError
            ? 'artefact introuvable'
            : meta.data
              ? `${meta.data.extension.toUpperCase()} · ${humanFileSize(meta.data.size_bytes)}`
              : '…'}
        </span>
      </div>
      <div className="artifact-chip-actions">
        <button
          type="button"
          className="tag"
          onClick={() => void download()}
          disabled={!meta.data}
          data-testid="artifact-chip-download"
        >
          <DownloadSimple size={14} weight="duotone" /> Télécharger
        </button>
        {isImage && (
          <button
            type="button"
            className="tag"
            onClick={() => void openFullscreen()}
            data-testid="artifact-chip-fullscreen"
          >
            <ArrowsOut size={14} weight="duotone" /> Plein écran
          </button>
        )}
        <button
          type="button"
          className="tag"
          onClick={() => void open()}
          data-testid="artifact-chip-open"
        >
          <ArrowSquareOut size={14} weight="duotone" /> Ouvrir
        </button>
      </div>
      {fullUrl && (
        <FullscreenOverlay label={name} onClose={() => setFullUrl(null)}>
          <img src={fullUrl} alt={name} />
        </FullscreenOverlay>
      )}
    </div>
  )
}

/** Bloc BlockNote custom `artifactChip` — une ligne `[label](artifact://uuid)`
 *  seule devient cette puce ; le label vide retombe sur le nom de fichier. */
export const ArtifactChipBlock = createReactBlockSpec(
  {
    type: 'artifactChip',
    propSchema: {
      id: { default: '' },
      label: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <ArtifactChipView id={props.block.props.id} label={props.block.props.label} />
    ),
  },
)
