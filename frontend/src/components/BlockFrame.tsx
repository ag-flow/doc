import { useState, type ReactNode } from 'react'
import { Check, Copy, Download, Pencil } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Édition en place de la source d'un bloc custom (corps + attributs). */
export interface BlockFrameEdit {
  /** Ligne d'attributs (info string) ; undefined = composant sans attributs. */
  attrs?: string
  /** Corps brut du bloc. */
  body: string
  onApply: (next: { attrs: string; body: string }) => void
}

interface BlockFrameProps {
  /** Titre affiché (attribut title du composant) ; repli sur typeLabel. */
  title?: string | null
  /** Libellé court du type (mermaid, timeline, chart, dataset…). */
  typeLabel: string
  /** Source markdown du bloc — action « copier la source ». */
  source: string
  /** Si fourni et non-null au clic : téléchargement SVG ; sinon `.md`. */
  svg?: () => string | null
  /** Fourni = bloc éditable en place (crayon) — uniquement en mode édition. */
  edit?: BlockFrameEdit
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

/** Panneau d'édition de la source : attributs (une ligne) + corps (records). */
function EditPanel({ edit, onClose }: { edit: BlockFrameEdit; onClose: () => void }) {
  const { t } = useTranslation()
  const [attrs, setAttrs] = useState((edit.attrs ?? '').trim())
  const [body, setBody] = useState(edit.body)
  return (
    <div className="border-t border-gray-100 p-3" data-testid="blockframe-edit-panel">
      {edit.attrs !== undefined && (
        <label className="mb-2 block">
          <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-gray-400">
            {t('blockFrame.attrs')}
          </span>
          <input
            value={attrs}
            onChange={(e) => setAttrs(e.target.value)}
            placeholder={t('blockFrame.attrsHint')}
            className="w-full rounded border border-gray-200 px-2 py-1 font-mono text-xs"
            data-testid="blockframe-edit-attrs"
          />
        </label>
      )}
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={Math.min(14, Math.max(4, body.split('\n').length + 1))}
        className="w-full resize-y rounded border border-gray-200 px-2 py-1 font-mono text-xs"
        data-testid="blockframe-edit-body"
      />
      <div className="mt-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-gray-200 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          {t('blockFrame.cancel')}
        </button>
        <button
          type="button"
          onClick={() => {
            // L'info string porte un espace de tête (```df-x title="…").
            const line = attrs.trim() ? ' ' + attrs.trim() : ''
            edit.onApply({ attrs: line, body })
            onClose()
          }}
          className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
          data-testid="blockframe-edit-apply"
        >
          {t('blockFrame.apply')}
        </button>
      </div>
    </div>
  )
}

/**
 * Chrome commun des blocs custom (spec 40_MCMP) : en-tête discret avec titre,
 * copie de la source markdown, téléchargement (SVG pour les rendus graphiques,
 * `.md` sinon) et — en mode édition — modification en place de la source
 * (crayon). UN SEUL chrome pour tous les codecs.
 */
export function BlockFrame({ title, typeLabel, source, svg, edit, children }: BlockFrameProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)

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
        <span className="ml-auto flex items-center gap-0.5 opacity-0 transition-opacity group-hover/frame:opacity-100 focus-within:opacity-100">
          {edit && (
            <button
              type="button"
              onClick={() => setEditing((e) => !e)}
              title={t('blockFrame.edit')}
              className={`rounded p-1 hover:bg-gray-200 hover:text-gray-700 ${
                editing ? 'text-indigo-600' : 'text-gray-400'
              }`}
              data-testid="blockframe-edit"
            >
              <Pencil size={13} />
            </button>
          )}
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
      {editing && edit && <EditPanel edit={edit} onClose={() => setEditing(false)} />}
    </div>
  )
}
