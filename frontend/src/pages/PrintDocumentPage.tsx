import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Printer } from '@phosphor-icons/react'
import { docsApi, type DocumentOut } from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { surfaceFor } from '../lib/contentSurfaces'
import {
  tileGrid,
  TILE_WARN_THRESHOLD,
  type FlowBlock,
  type PrintLayout,
  type Tile,
} from '../lib/print/layout'
import { stripTitleHeading } from '../lib/markdownTitle'
import { Button } from '../components/ui/button'
import { SheetSkeleton } from '../components/ui/states'

/** Hauteur utile d'une page A4 avec marges 16 mm (297 − 2×16). */
const PAGE_HEIGHT_MM = 265
/** Largeur utile d'une page A4 avec marges 16 mm (210 − 2×16). */
const PAGE_WIDTH_MM = 178

/** Blocs à ajuster : composants encadrés (df-*, mermaid…), tableaux, code,
 *  images — les éléments nus déjà couverts par un cadre sont exclus. */
const FIT_SELECTOR = '[data-content-type], table, pre, img'

/** Facteur de réduction pour tenir sur une page (96 % de marge de sûreté),
 *  borné à 35 % — en dessous, le composant deviendrait illisible. */
export function fitFactor(height: number, pageHeight: number): number {
  if (height <= pageHeight) return 1
  return Math.max(0.35, (pageHeight * 0.96) / height)
}

/** Ré-exporté depuis le module neutre : la page n'est plus propriétaire du type,
 *  les surfaces le produisent. Les imports existants restent valides. */
export type { FlowBlock }

/**
 * Positions des coupures de page pour l'APERÇU, en simulant la pagination réelle
 * du PDF : une coupure ne tombe jamais dans un composant insécable (elle recule
 * avant lui) ni juste après un titre (elle recule avant le titre). Reproduit,
 * côté aperçu, ce que `break-inside/after: avoid` produit à l'impression.
 */
export function computeCuts(blocks: FlowBlock[], pageH: number, contentHeight: number): number[] {
  if (pageH <= 0) return []
  const cuts: number[] = []
  let pageStart = 0
  let guard = 0
  while (pageStart + pageH < contentHeight - 1 && guard++ < 2000) {
    let cut = pageStart + pageH
    let changed = true
    let iter = 0
    while (changed && iter++ < 100) {
      changed = false
      // Règle A : ne pas trancher un composant qui commence sur cette page.
      const comp = blocks.find(
        (b) =>
          b.kind === 'component' &&
          b.top > pageStart + 0.5 &&
          b.top < cut - 0.5 &&
          b.bottom > cut + 0.5,
      )
      if (comp) {
        cut = comp.top
        changed = true
        continue
      }
      // Règle B : un titre ne peut pas être le dernier bloc de la page. Si le
      // bloc juste au-dessus de la coupure est un titre sans contenu entre lui
      // et la coupure, on recule avant le titre.
      const above = blocks
        .filter((b) => b.bottom <= cut + 0.5 && b.top >= pageStart - 0.5)
        .sort((a, b) => b.bottom - a.bottom)[0]
      if (above && above.kind === 'heading' && above.top > pageStart + 0.5) {
        const between = blocks.some(
          (b) => b !== above && b.top >= above.bottom - 0.5 && b.top < cut - 0.5,
        )
        if (!between) {
          cut = above.top
          changed = true
        }
      }
    }
    // Sécurité : aucune coupure meilleure trouvée (ex. bloc plus haut qu'une
    // page malgré le zoom) → coupure naïve, on avance.
    if (cut <= pageStart + 0.5) cut = pageStart + pageH
    cuts.push(cut)
    pageStart = cut
  }
  return cuts
}

/**
 * Découpe d'une section, d'après le régime déclaré par sa surface.
 *
 * `flow` → coupures calculées ; `plane` → tuiles. Une surface qui ne déclare
 * rien est traitée en `plane` mesuré sur sa boîte : on tuile plutôt que de
 * trancher au hasard. Un repli qui tuile consomme du papier, ce qui se voit ;
 * un repli qui tronque ne se voit pas — c'était le défaut réparé par ce lot.
 */
function sectionLayout(section: HTMLElement, contentType: string | null): PrintLayout {
  const host = section.querySelector<HTMLElement>('[data-print-content]') ?? section
  const declared = surfaceFor(contentType).getPrintLayout?.(host)
  if (declared) return declared
  return { mode: 'plane', width: host.scrollWidth, height: host.scrollHeight }
}

/**
 * Vue d'impression (export PDF sans Chromium serveur) : la page rend le
 * document et les enfants choisis avec le VRAI moteur de l'application —
 * composants graphiques compris (df-chart, mermaid, df-display…) — dans un
 * onglet dédié sans chrome. L'aperçu est calé sur la largeur imprimable et
 * porte des repères de coupure de page ; l'utilisateur vérifie puis déclenche
 * l'impression du navigateur (destination « Enregistrer en PDF »).
 */
/** Feuille de contenu d'un document, rendue dans la surface de son type de
 *  contenu (repli texte brut si le type est inconnu).
 *
 *  `forPrint` est ce qui rend l'impression HONNÊTE pour une surface qui n'offre
 *  normalement qu'une fenêtre de visualisation : elle rend alors son contenu
 *  entier. Sans lui, un diagramme n'imprimait que son hublot — et aucune
 *  pagination n'aurait pu rattraper ce qui n'était pas dans le DOM.
 *
 */
function PrintViewer({ doc }: { doc: DocumentOut }) {
  const { Viewer } = surfaceFor(doc.type)
  return (
    <Viewer
      content={stripTitleHeading(doc.content ?? '', doc.title)}
      bare
      docId={doc.doc_technical_key}
      forPrint
    />
  )
}

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
  const [tiles, setTiles] = useState<Record<string, Tile[]>>({})
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
    // Largeur utile A4 (210 − 2×16). Sondée de même : c'est le navigateur qui
    // convertit les millimètres, pas nous.
    const wProbe = document.createElement('div')
    wProbe.style.cssText = `width:${PAGE_WIDTH_MM}mm;position:absolute;visibility:hidden`
    host.appendChild(wProbe)
    const pageWidthPx = wProbe.offsetWidth
    wProbe.remove()
    probe.remove()
    if (pageHeightPx <= 0 || pageWidthPx <= 0) return

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
      const nextTiles: Record<string, Tile[]> = {}
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
        // La surface déclare son régime ; la page ne fait que découper.
        const layout = sectionLayout(section, section.dataset.contentType ?? null)
        if (layout.mode === 'plane') {
          // Un plan ne se coupe pas : il se tuile. Les tuiles sont émises dans le
          // flux d'impression (une par page) — aucune CSS ne tuile horizontalement,
          // ce qui dépasse la largeur d'une page est purement et simplement rogné.
          nextTiles[id] = tileGrid(layout.width, layout.height, pageWidthPx, pageHeightPx)
          next[id] = []
        } else {
          nextTiles[id] = []
          next[id] = computeCuts(layout.blocks, pageHeightPx, section.offsetHeight)
        }
        running += section.offsetHeight
      })
      setMarkers((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
      setTiles((prev) => (JSON.stringify(prev) === JSON.stringify(nextTiles) ? prev : nextTiles))
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

  // Nombre de pages : une par tuile en régime plan, une par coupure + 1 en flux.
  // Annoncé plutôt que subi — c'est la seule façon de voir venir une impression
  // absurde avant de l'avoir lancée.
  const pageCount = docs.reduce((total, d) => {
    const id = d.doc_technical_key
    const tileCount = (tiles[id] ?? []).length
    return total + (tileCount > 0 ? tileCount : (markers[id] ?? []).length + 1)
  }, 0)

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
        <span className="shrink-0 text-[13px] text-ink/[0.6]" data-testid="print-page-count">
          {pageCount} page{pageCount > 1 ? 's' : ''}
        </span>
        {pageCount > TILE_WARN_THRESHOLD && (
          <span
            className="tag tag-accent-2 shrink-0"
            data-testid="print-page-warning"
            title="Un diagramme large est tuilé à sa taille réelle : réduisez-le ou imprimez une partie."
          >
            impression longue
          </span>
        )}
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
              data-content-type={d.type}
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
              <div data-print-content>
                <PrintViewer doc={d} />
              </div>
              {/* Grille de tuilage : repères d'aperçu seulement. Les tuiles
                  imprimées, elles, sont émises plus bas. */}
              {(tiles[d.doc_technical_key] ?? []).map((t) => (
                <div
                  key={`${t.col}:${t.row}`}
                  className="tile-marker no-print"
                  style={{ left: t.x, top: t.y }}
                  data-testid={`tile-marker-${d.doc_technical_key}-${t.col}-${t.row}`}
                >
                  <span className="tile-marker-label">
                    col. {t.col} / ligne {t.row}
                  </span>
                </div>
              ))}
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
