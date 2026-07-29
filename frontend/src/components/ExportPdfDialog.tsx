import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp } from '@phosphor-icons/react'
import { api, docsApi, ApiError, type DocumentOut } from '../lib/api'
import { Button } from './ui/button'

interface Props {
  ws: string
  blocSlug: string
  docId: string
  /** Nom de fichier proposé (slug du document, repli titre). */
  filename: string
  onClose: () => void
}

interface ChildRow {
  id: string
  title: string
  checked: boolean
}

/**
 * Export PDF : le document seul, ou avec ses enfants directs — chacun cochable
 * et ordonnable (l'ordre choisi est l'ordre du PDF). « Document signé » ajoute
 * un cadre de signatures en fin de document. Le PDF se télécharge directement.
 */
export function ExportPdfDialog({ ws, blocSlug, docId, filename, onClose }: Props) {
  const { t } = useTranslation()
  const [scope, setScope] = useState<'doc' | 'children'>('doc')
  const [signed, setSigned] = useState(false)
  const [rows, setRows] = useState<ChildRow[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: blockDocs = [] } = useQuery<DocumentOut[]>({
    queryKey: ['block-documents', ws, blocSlug],
    queryFn: () => docsApi.getBlockDocuments(ws, blocSlug),
  })

  // Enfants directs, tous cochés par défaut, dans l'ordre du bloc — ensuite
  // l'utilisateur coche/décoche et réordonne librement. Garde `length === 0` :
  // pendant le chargement, le défaut `[]` change d'identité à chaque rendu —
  // un setState inconditionnel bouclerait.
  useEffect(() => {
    if (blockDocs.length === 0) return
    setRows((prev) => {
      if (prev.length > 0) return prev
      return blockDocs
        .filter((d) => d.parent_id === docId)
        .map((d) => ({ id: d.doc_technical_key, title: d.title, checked: true }))
    })
  }, [blockDocs, docId])

  function move(index: number, delta: -1 | 1) {
    setRows((prev) => {
      const next = [...prev]
      const target = index + delta
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function download() {
    setPending(true)
    setError(null)
    const childIds = scope === 'children'
      ? rows.filter((r) => r.checked).map((r) => r.id)
      : []
    const params = new URLSearchParams()
    if (childIds.length > 0) params.set('children', childIds.join(','))
    if (signed) params.set('signed', 'true')
    const qs = params.toString()
    void api
      .getBlob(`/workspaces/${ws}/documents/${docId}/export/pdf${qs ? `?${qs}` : ''}`)
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${filename}.pdf`
        a.click()
        URL.revokeObjectURL(url)
        onClose()
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : t('error.generic'))
        setPending(false)
      })
  }

  return (
    <div className="dialog-backdrop z-50" onClick={onClose} data-testid="export-pdf-dialog">
      <div className="dialog" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h4 className="dialog-title">{t('exportPdf.title')}</h4>

        <div className="grid gap-1.5">
          <label className="flex items-center gap-2 text-[14px]">
            <input type="radio" name="pdf-scope" checked={scope === 'doc'}
              onChange={() => setScope('doc')} data-testid="pdf-scope-doc" />
            {t('exportPdf.scopeDoc')}
          </label>
          <label className="flex items-center gap-2 text-[14px]">
            <input type="radio" name="pdf-scope" checked={scope === 'children'}
              onChange={() => setScope('children')} data-testid="pdf-scope-children" />
            {t('exportPdf.scopeChildren')}
          </label>
        </div>

        {scope === 'children' && (
          rows.length === 0 ? (
            <p className="dialog-body m-0">{t('exportPdf.noChildren')}</p>
          ) : (
            <div>
              <p className="m-0 mb-1.5 text-[12px] text-ink/[0.55]">{t('exportPdf.childrenHint')}</p>
              <ul className="dialog-scroll m-0 max-h-[220px] list-none overflow-y-auto p-0">
                {rows.map((r, i) => (
                  <li key={r.id}
                    className="flex items-center gap-2 border-b border-[var(--color-divider)] py-1 last:border-b-0"
                    data-testid={`pdf-child-${r.id}`}>
                    <input
                      type="checkbox"
                      checked={r.checked}
                      onChange={() =>
                        setRows((prev) =>
                          prev.map((x) => (x.id === r.id ? { ...x, checked: !x.checked } : x)),
                        )
                      }
                      data-testid={`pdf-child-check-${r.id}`}
                    />
                    <span className="min-w-0 flex-1 truncate text-[14px]">{r.title}</span>
                    <Button variant="icon" size="sm" title={t('exportPdf.moveUp')}
                      disabled={i === 0} onClick={() => move(i, -1)}
                      data-testid={`pdf-child-up-${r.id}`}>
                      <ArrowUp size={13} weight="duotone" />
                    </Button>
                    <Button variant="icon" size="sm" title={t('exportPdf.moveDown')}
                      disabled={i === rows.length - 1} onClick={() => move(i, 1)}>
                      <ArrowDown size={13} weight="duotone" />
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )
        )}

        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={signed} onChange={(e) => setSigned(e.target.checked)}
            data-testid="pdf-signed" />
          {t('exportPdf.signed')}
        </label>

        <div aria-live="polite" className="empty:hidden">
          {error && <p className="field-error m-0">{error}</p>}
        </div>

        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={download} disabled={pending} data-testid="pdf-validate">
            {pending ? t('exportPdf.pending') : t('exportPdf.validate')}
          </Button>
        </div>
      </div>
    </div>
  )
}
