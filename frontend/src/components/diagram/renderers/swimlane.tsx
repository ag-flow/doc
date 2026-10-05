/** Rendu `df-diagram type="swimlane"` (alias `process`) — flux cross-fonctionnel :
 *  une rangée par rôle (lane), une colonne par étape séquentielle, connecteurs
 *  entre étapes consécutives. Corps : `Lane | Étape` par ligne, ordre = séquence. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { lanes, type Rect } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Edge } from '../Edge'
import { Label } from '../Label'
import { Node } from '../Node'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const PAD = 8
const LANE_LABEL_W = 84
const NODE_W = 88
const NODE_H = 26
const H_GAP = 26
const ROW_H = 46
const ROW_GAP = 6

export function SwimlaneDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 2 })
  const steps = parsed.rows.filter((r) => r[0].length > 0 && r[1].length > 0)
  const ignored = parsed.rows.length - steps.length
  if (steps.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  // Lanes dans l'ordre de première apparition.
  const laneNames: string[] = []
  for (const [lane] of steps) if (!laneNames.includes(lane)) laneNames.push(lane)

  const contentX0 = PAD + LANE_LABEL_W
  const stepX = (col: number) => contentX0 + col * (NODE_W + H_GAP) + NODE_W / 2
  const W = contentX0 + steps.length * (NODE_W + H_GAP) - H_GAP + PAD

  const area: Rect = {
    x: PAD,
    y: PAD,
    width: W - 2 * PAD,
    height: laneNames.length * ROW_H + (laneNames.length - 1) * ROW_GAP,
  }
  const { bands, centers } = lanes({ area, count: laneNames.length, orientation: 'horizontal', gap: ROW_GAP })
  const H = area.height + 2 * PAD
  const laneCenterY = (lane: string) => centers[laneNames.indexOf(lane)]

  const laneEls: ReactNode[] = bands.map((b, i) => (
    <g key={`l${i}`} data-diagram="lane">
      <rect
        x={b.x}
        y={b.y}
        width={b.width}
        height={b.height}
        rx={DIAGRAM.radius}
        fill="none"
        stroke={DIAGRAM.hairlineColor}
        strokeWidth={DIAGRAM.hairlineWidth}
      />
      <Label x={b.x + 6} y={b.y + b.height / 2} anchor="start" variant="muted" size={10}>
        {laneNames[i]}
      </Label>
    </g>
  ))

  const edgeEls: ReactNode[] = steps.slice(1).map((_, i) => (
    <Edge
      key={`e${i}`}
      from={{ x: stepX(i) + NODE_W / 2, y: laneCenterY(steps[i][0]) }}
      to={{ x: stepX(i + 1) - NODE_W / 2, y: laneCenterY(steps[i + 1][0]) }}
      variant="orthogonal"
      arrow
    />
  ))

  const stepEls: ReactNode[] = steps.map(([lane, step], i) => (
    <Node
      key={`s${i}`}
      rect={{ x: stepX(i) - NODE_W / 2, y: laneCenterY(lane) - NODE_H / 2, width: NODE_W, height: NODE_H }}
      label={step}
    />
  ))

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 480 }} role="img">
        {laneEls}
        {edgeEls}
        {stepEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
