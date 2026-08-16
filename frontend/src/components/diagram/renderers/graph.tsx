/** Rendu `df-diagram type="graph"` (et alias sémantiques : architecture,
 *  dataflow, dp-integration, high-level, it-current-state, medallion).
 *  Graphe orienté en couches. Attribut `dir="LR"` (défaut) ou `"TB"`. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseGraph } from '../../../lib/blockCodecs/graphSpec'
import { layeredGraph, type Rect } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Edge } from '../Edge'
import { Label } from '../Label'
import { Node } from '../Node'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

/** Marge réservée en haut du viewBox quand un self-loop est sur la rangée du
 *  haut (son arc/label montent à `y - 26` : sans marge, ils seraient clippés). */
const SELF_LOOP_TOP_MARGIN = 30

/** Extrémités d'une arête selon le sens (sortie source → entrée cible). */
function endpoints(from: Rect, to: Rect, lr: boolean) {
  if (lr) {
    return {
      a: { x: from.x + from.width, y: from.y + from.height / 2 },
      b: { x: to.x, y: to.y + to.height / 2 },
    }
  }
  return {
    a: { x: from.x + from.width / 2, y: from.y + from.height },
    b: { x: to.x + to.width / 2, y: to.y },
  }
}

export function GraphDiagram({ body, conf, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const { nodes, edges, ignored } = parseGraph(body)
  if (nodes.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const dir = conf.dir === 'TB' ? 'TB' : 'LR'
  const lr = dir === 'LR'
  const { placed, width, height } = layeredGraph(nodes, edges, { dir })

  // Un self-loop sur un nœud de la rangée du haut monte au-dessus de y=0 :
  // on décale l'origine du viewBox pour ne pas le clipper, sans déplacer
  // les éléments eux-mêmes.
  const minY = Math.min(...Array.from(placed.values()).map((r) => r.y))
  const hasTopSelfLoop = edges.some((e) => e.from === e.to && placed.get(e.from)?.y === minY)
  const topMargin = hasTopSelfLoop ? SELF_LOOP_TOP_MARGIN : 0

  const edgeEls: ReactNode[] = edges.map((e, i) => {
    const from = placed.get(e.from)
    const to = placed.get(e.to)
    if (!from || !to) return null
    // Self-loop (A→A, ex. state machine) : petit arc au-dessus du nœud.
    if (e.from === e.to) {
      const x1 = from.x + from.width * 0.35
      const x2 = from.x + from.width * 0.65
      const yTop = from.y
      const d = `M${x1} ${yTop} C ${x1} ${yTop - 22} ${x2} ${yTop - 22} ${x2} ${yTop}`
      return (
        <g key={`e${i}`} data-diagram="self-loop">
          <path d={d} fill="none" stroke={DIAGRAM.ink} strokeWidth={DIAGRAM.hairlineWidth} />
          <path d={`M${x2} ${yTop} l-3 -4 l5 1 Z`} fill={DIAGRAM.ink} />
          {e.label && (
            <Label x={(x1 + x2) / 2} y={yTop - 26} anchor="middle" variant="muted" size={9}>
              {e.label}
            </Label>
          )}
        </g>
      )
    }
    const { a, b } = endpoints(from, to, lr)
    return (
      <g key={`e${i}`}>
        <Edge from={a} to={b} variant="orthogonal" arrow />
        {e.label && (
          <Label x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 4} anchor="middle" variant="muted" size={9}>
            {e.label}
          </Label>
        )}
      </g>
    )
  })

  const nodeEls: ReactNode[] = nodes.map((n) => {
    const rect = placed.get(n.id)!
    return <Node key={n.id} rect={rect} label={n.label} sublabel={n.group || undefined} />
  })

  return (
    <>
      <svg
        ref={svgRef}
        viewBox={`0 ${-topMargin} ${width} ${height + topMargin}`}
        className="w-full"
        style={{ maxHeight: 480 }}
        role="img"
      >
        {edgeEls}
        {nodeEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
