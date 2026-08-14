/** Rendu `df-diagram type="loop"` — flywheel : stations en anneau reliées en
 *  cycle, avec un hub central optionnel (write-backs en pointillés).
 *  Corps : une station par ligne. Attribut `hub="Nom"` pour le hub partagé. */
import type { ReactNode } from 'react'
import { radialPoints, type Point } from '../../../lib/diagramLayout'
import { Edge } from '../Edge'
import { Node } from '../Node'
import type { RendererProps } from './types'

const W = 320
const H = 300
const R = 104
const NODE_W = 84
const NODE_H = 28

export function LoopDiagram({ body, conf, svgRef }: RendererProps) {
  const stations = body
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
  if (stations.length < 2) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const cx = W / 2
  const cy = H / 2
  const pts = radialPoints({ cx, cy, radius: R, count: stations.length, startAngleDeg: -90 })
  const hub = (conf.hub ?? '').trim()
  const rectAt = (p: Point) => ({ x: p.x - NODE_W / 2, y: p.y - NODE_H / 2, width: NODE_W, height: NODE_H })

  // Arêtes du cycle (station i → i+1).
  const cycleEls: ReactNode[] = pts.map((p, i) => {
    const next = pts[(i + 1) % pts.length]
    return <Edge key={`c${i}`} from={p} to={next} arrow />
  })

  // Write-backs vers le hub (pointillés) si hub défini.
  const spokeEls: ReactNode[] = hub
    ? pts.map((p, i) => <Edge key={`s${i}`} from={p} to={{ x: cx, y: cy }} dashed />)
    : []

  const stationEls: ReactNode[] = pts.map((p, i) => <Node key={`n${i}`} rect={rectAt(p)} label={stations[i]} />)

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 340 }} role="img">
        {cycleEls}
        {spokeEls}
        {hub && <Node rect={rectAt({ x: cx, y: cy })} label={hub} variant="focal" />}
        {stationEls}
      </svg>
    </>
  )
}
