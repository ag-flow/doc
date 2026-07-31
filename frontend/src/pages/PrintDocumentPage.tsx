import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Printer } from '@phosphor-icons/react'
import { docsApi, type DocumentOut } from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { MarkdownViewer } from '../components/MarkdownViewer'
import { stripTitleHeading } from '../lib/markdownTitle'
import { Button } from '../components/ui/button'
import { SheetSkeleton } from '../components/ui/states'

/** Hauteur utile d'une page A4 avec marges 16 mm (297 − 2×16). */
const PAGE_HEIGHT_MM = 265

/**
 * Vue d'impression (export PDF sans Chromium serveur) : la page rend le
 * document et les enfants choisis avec le VRAI moteur de l'application —
 * composants graphiques compris (df-chart, mermaid, df-display…) — dans un
 * onglet dédié sans chrome. L'aperçu est calé sur la largeur imprimable et
 * porte des repères de coupure de page ; l'utilisateur vérifie puis déclenche
 * l'impression du navigateur (destination « Enregistrer en PDF »).
 */
export function PrintDocumentPage() {
  const { wsSlug: ws, docId } = useParams<{ wsSlug: string; blocSlug: string; docId: string }>()
  const [params] = useSearchParams()
  const signed = params.get('signed') === 'true'
  const childrenParam = params.get('children') ?? ''

  // Les blocs branchés sur un dataset résolvent le workspace via le contexte.
  const { setCurrentSlug } = useWorkspace()
  useEffect(() => {
    if (ws) setCurrentSlug(ws)
  }, [ws, setCurrentSlug])

  const ids = useMemo(
    () => [docId!, ...childrenParam.split(',').filter(Boolean)],
    [docId, childrenParam],
  )

  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['document', ws, id],
      queryFn: () => docsApi.getDocument(ws!, id),
      enabled: Boolean(ws && id),
    })),
  })
  const loading = queries.some((q) => q.isLoading)
  const failed = queries.some((q) => q.isError)
  const docs = queries
    .map((q) => q.data)
    .filter((d): d is DocumentOut => Boolean(d))

  // ── Repères de coupure : chaque section imprime sur SA page (print-break),
  // les coupures se mesurent donc PAR section. Re-mesure après le rendu
  // asynchrone des diagrammes (mermaid/charts) via ResizeObserver + passes
  // différées. Repère indicatif : l'insécabilité des composants à
  // l'impression peut décaler légèrement la coupure réelle.
  const pagesRef = useRef<HTMLDivElement>(null)
  const [markers, setMarkers] = useState<Record<string, number[]>>({})

  useEffect(() => {
    const host = pagesRef.current
    if (!host || loading) return

    // 265 mm convertis en pixels par le navigateur lui-même (sonde).
    const probe = document.createElement('div')
    probe.style.cssText = `height:${PAGE_HEIGHT_MM}mm;position:absolute;visibility:hidden`
    host.appendChild(probe)
    const pageHeightPx = probe.offsetHeight
    probe.remove()
    if (pageHeightPx <= 0) return

    const measure = () => {
      const next: Record<string, number[]> = {}
      host.querySelectorAll<HTMLElement>('.print-sheet').forEach((section) => {
        const id = section.dataset.docId
        if (!id) return
        const tops: number[] = []
        for (let y = pageHeightPx; y < section.offsetHeight; y += pageHeightPx) {
          tops.push(y)
        }
        next[id] = tops
      })
      setMarkers((prev) =>
        JSON.stringify(prev) === JSON.stringify(next) ? prev : next,
      )
    }

    measure()
    // Diagrammes asynchrones : re-mesures différées + observation des tailles.
    const timers = [500, 1500, 3500].map((ms) => setTimeout(measure, ms))
    const observer = new ResizeObserver(measure)
    host.querySelectorAll<HTMLElement>('.print-sheet').forEach((s) => observer.observe(s))
    return () => {
      timers.forEach(clearTimeout)
      observer.disconnect()
    }
  }, [loading, docs.length])

  return (
    <div className="print-page" data-testid="print-page">
      <div className="no-print print-toolbar">
        <p className="m-0 min-w-0 flex-1 text-[13px] text-ink/[0.6]">
          Aperçu avant impression — largeur réelle A4, traits magenta = coupures
          de page (indicatifs : un composant insécable peut décaler la coupure).
          Vérifiez le rendu puis imprimez en choisissant « Enregistrer en PDF ».
        </p>
        <Button onClick={() => window.print()} data-testid="print-btn">
          <Printer size={15} weight="duotone" /> Imprimer / PDF
        </Button>
      </div>

      {failed && (
        <p className="field-error" data-testid="print-error">
          Impossible de charger un des documents demandés.
        </p>
      )}
      {loading ? (
        <SheetSkeleton />
      ) : (
        <div ref={pagesRef}>
          {docs.map((d, i) => (
            <section
              key={d.doc_technical_key}
              data-doc-id={d.doc_technical_key}
              className={`doc-sheet wiki-prose print-sheet${i > 0 ? ' print-break' : ''}`}
              data-testid={`print-doc-${d.doc_technical_key}`}
            >
              {(markers[d.doc_technical_key] ?? []).map((top, page) => (
                <div
                  key={top}
                  className="page-marker no-print"
                  style={{ top }}
                  data-testid={`page-marker-${d.doc_technical_key}-${page}`}
                >
                  <span className="page-marker-label">fin p. {page + 1}</span>
                </div>
              ))}
              <h1>{d.title}</h1>
              <MarkdownViewer content={stripTitleHeading(d.content ?? '', d.title)} bare />
            </section>
          ))}
          {signed && (
            <section className="print-signatures" data-testid="print-signatures">
              <h2>Signatures</h2>
              <table>
                <tbody>
                  <tr>
                    <td className="sig-label">Nom</td>
                    <td className="sig-label">Date</td>
                    <td className="sig-label">Signature</td>
                  </tr>
                  <tr><td /><td /><td /></tr>
                </tbody>
              </table>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
