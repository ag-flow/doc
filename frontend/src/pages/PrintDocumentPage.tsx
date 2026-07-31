import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
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

/** Blocs à ajuster : composants encadrés (df-*, mermaid…), tableaux, code,
 *  images — les éléments nus déjà couverts par un cadre sont exclus. */
const FIT_SELECTOR = '[data-content-type], table, pre, img'

/** Facteur de réduction pour tenir sur une page (96 % de marge de sûreté),
 *  borné à 35 % — en dessous, le composant deviendrait illisible. */
export function fitFactor(height: number, pageHeight: number): number {
  if (height <= pageHeight) return 1
  return Math.max(0.35, (pageHeight * 0.96) / height)
}

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
  // Remplissage (aperçu écran) poussant chaque document suivant en haut d'une
  // nouvelle page — pour que l'aperçu reflète la coupure par document du PDF.
  const [fills, setFills] = useState<Record<string, number>>({})

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

    // Un composant plus haut qu'une page ne PEUT pas tenir : on le réduit
    // (zoom, qui contracte aussi la boîte de layout) pour qu'il rentre. Le
    // reset préalable redonne la hauteur naturelle — la réduction reste
    // idempotente entre deux passes.
    const fitOversized = () => {
      host.querySelectorAll<HTMLElement>(FIT_SELECTOR).forEach((el) => {
        const frame = el.closest('[data-content-type]')
        if (frame && frame !== el) return // le cadre parent porte l'ajustement
        el.style.zoom = ''
        const factor = fitFactor(el.offsetHeight, pageHeightPx)
        if (factor < 1) {
          el.style.zoom = factor.toFixed(3)
          el.title = `Réduit à ${Math.round(factor * 100)} % pour tenir sur une page`
          el.dataset.printZoomed = String(Math.round(factor * 100))
        } else if (el.dataset.printZoomed) {
          delete el.dataset.printZoomed
          el.removeAttribute('title')
        }
      })
    }

    let observer: ResizeObserver | null = null
    const observeSheets = () =>
      host.querySelectorAll<HTMLElement>('.print-sheet').forEach((s) => observer?.observe(s))

    const measure = () => {
      // L'ajustement modifie les hauteurs : suspendre l'observation pour ne
      // pas boucler sur nos propres écritures.
      observer?.disconnect()
      fitOversized()
      const next: Record<string, number[]> = {}
      const nextFills: Record<string, number> = {}
      // Hauteur cumulée depuis le haut du 1er document (origine des repères de
      // page). Chaque document suivant est repoussé en haut de la page suivante.
      let running = 0
      host.querySelectorAll<HTMLElement>('.print-sheet').forEach((section, index) => {
        const id = section.dataset.docId
        if (!id) return
        if (index > 0) {
          const pad = (pageHeightPx - (running % pageHeightPx)) % pageHeightPx
          nextFills[id] = Math.round(pad)
          running += pad
        }
        const tops: number[] = []
        for (let y = pageHeightPx; y < section.offsetHeight; y += pageHeightPx) {
          tops.push(y)
        }
        next[id] = tops
        running += section.offsetHeight
      })
      setMarkers((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
      setFills((prev) => (JSON.stringify(prev) === JSON.stringify(nextFills) ? prev : nextFills))
      observeSheets()
    }

    observer = new ResizeObserver(measure)
    measure()
    // Diagrammes asynchrones : re-mesures différées en plus de l'observation.
    const timers = [500, 1500, 3500].map((ms) => setTimeout(measure, ms))
    return () => {
      timers.forEach(clearTimeout)
      observer?.disconnect()
    }
  }, [loading, docs.length])

  return (
    <div className="print-page" data-testid="print-page">
      <div className="no-print print-toolbar">
        <p className="m-0 min-w-0 flex-1 text-[13px] text-ink/[0.6]">
          Aperçu avant impression — largeur réelle A4, traits magenta = coupures
          de page (indicatives : à l'impression, un composant insécable est reporté
          seul sur la page suivante et un titre n'est jamais laissé seul en bas de
          page — il descend avec son contenu). Un composant plus haut qu'une page
          est réduit pour y tenir. Vérifiez le rendu puis imprimez en choisissant
          « Enregistrer en PDF ».
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
            <Fragment key={d.doc_technical_key}>
              {i > 0 && (
                <div
                  className="page-fill no-print"
                  style={{ height: fills[d.doc_technical_key] ?? 0 }}
                  data-testid={`page-fill-${d.doc_technical_key}`}
                >
                  <span className="page-fill-label">page suivante</span>
                </div>
              )}
            <section
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
            </Fragment>
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
