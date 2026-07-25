import { useState, type ReactNode } from 'react'
import { Check, Copy, Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface BlockFrameProps {
  /** Titre affiché (attribut title du composant) ; repli sur typeLabel. */
  title?: string | null
  /** Libellé court du type (mermaid, timeline, chart, dataset…). */
  typeLabel: string
  /** Source markdown du bloc — action « copier la source ». */
  source: string
  /** Si fourni et non-null au clic : téléchargement SVG ; sinon `.md`. */
  svg?: () => string | null
  children: ReactNode
}

function downloadBlob(filename: string, data: string, mime: string) {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Chrome commun des blocs custom (spec 40_MCMP) : en-tête discret avec titre,
 * copie de la source markdown et téléchargement (SVG pour les rendus
 * graphiques, `.md` sinon). UN SEUL chrome pour tous les codecs.
 */
export function BlockFrame({ title, typeLabel, source, svg, children }: BlockFrameProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  async function copySource() {
    try {
      await navigator.clipboard?.writeText(source)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* presse-papier indisponible */
    }
  }

  function download() {
    const base = (title || typeLabel).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || typeLabel
    const svgData = svg ? svg() : null
    if (svgData) downloadBlob(`${base}.svg`, svgData, 'image/svg+xml')
    else downloadBlob(`${base}.md`, source, 'text/markdown')
  }

  return (
    <div className="group/frame my-2 w-full rounded-lg border border-gray-200" data-content-type={typeLabel}>
      <div className="flex items-center gap-2 rounded-t-lg border-b border-gray-100 bg-gray-50 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{typeLabel}</span>
        {title && <span className="truncate text-xs font-medium text-gray-700">{title}</span>}
        <span className="ml-auto flex items-center gap-0.5 opacity-0 transition-opacity group-hover/frame:opacity-100">
          <button
            type="button"
            onClick={copySource}
            title={t('blockFrame.copy')}
            className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
            data-testid="blockframe-copy"
          >
            {copied ? <Check size={13} className="text-green-600" /> : <Copy size={13} />}
          </button>
          <button
            type="button"
            onClick={download}
            title={t('blockFrame.download')}
            className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
            data-testid="blockframe-download"
          >
            <Download size={13} />
          </button>
        </span>
      </div>
      <div className="p-3">{children}</div>
    </div>
  )
}
