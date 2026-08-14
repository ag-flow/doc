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
import type { RendererProps } from './types'

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

  const edgeEls: ReactNode[] = edges.map((e, i) => {
    const from = placed.get(e.from)
    const to = placed.get(e.to)
    if (!from || !to) return null
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
      <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 480 }} role="img">
        {edgeEls}
        {nodeEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
