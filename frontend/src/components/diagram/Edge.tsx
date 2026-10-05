/** Primitive Edge — connecteur entre deux points (droit ou orthogonal), avec
 *  tête de flèche et pointillés optionnels. À rendre dans un <svg>. */
import type { Point } from '../../lib/diagramLayout'
import { DIAGRAM } from './svgTokens'

export type EdgeVariant = 'straight' | 'orthogonal'

export interface EdgeProps {
  from: Point
  to: Point
  variant?: EdgeVariant
  /** Tête de flèche à l'extrémité `to`. Défaut false. */
  arrow?: boolean
  dashed?: boolean
  /** Épaisseur du trait (px). Défaut : token --diagram-hairline-width. */
  width?: number | string
  /** Bordure accent (mise en avant d'un lien focal). Défaut false. */
  focal?: boolean
}

/** Suite de points du tracé selon la variante (coude médian si orthogonal). */
function pathPoints(from: Point, to: Point, variant: EdgeVariant): Point[] {
  if (variant === 'orthogonal') {
    const midX = (from.x + to.x) / 2
    return [from, { x: midX, y: from.y }, { x: midX, y: to.y }, to]
  }
  return [from, to]
}

function toPathD(pts: Point[]): string {
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ')
}

/** Triangle de flèche à `tip`, orienté selon le dernier segment (`prev`→`tip`). */
function arrowHead(prev: Point, tip: Point, size = 6): string {
  const ang = Math.atan2(tip.y - prev.y, tip.x - prev.x)
  const a1 = ang + Math.PI - 0.4
  const a2 = ang + Math.PI + 0.4
  const p1 = { x: tip.x + size * Math.cos(a1), y: tip.y + size * Math.sin(a1) }
  const p2 = { x: tip.x + size * Math.cos(a2), y: tip.y + size * Math.sin(a2) }
  return `M${tip.x} ${tip.y} L${p1.x} ${p1.y} L${p2.x} ${p2.y} Z`
}

export function Edge({ from, to, variant = 'straight', arrow = false, dashed = false, width, focal = false }: EdgeProps) {
  const pts = pathPoints(from, to, variant)
  const stroke = focal ? DIAGRAM.accent : DIAGRAM.ink
  const strokeWidth = width ?? DIAGRAM.hairlineWidth
  return (
    <g data-diagram="edge" data-variant={variant}>
      <path
        d={toPathD(pts)}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeDasharray={dashed ? '4 3' : undefined}
      />
      {arrow && (
        <path data-diagram="arrow" d={arrowHead(pts[pts.length - 2], pts[pts.length - 1])} fill={stroke} />
      )}
    </g>
  )
}
