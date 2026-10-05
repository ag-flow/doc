/** Primitive Annotation — commentaire éditorial en sérif italique (esprit
 *  Instrument Serif de diagram-design), avec ligne de rappel optionnelle vers
 *  un point cible. À rendre dans un <svg>. */
import type { Point } from '../../lib/diagramLayout'
import type { Anchor } from './Label'
import { DIAGRAM } from './svgTokens'

export interface AnnotationProps {
  x: number
  y: number
  children: string
  anchor?: Anchor
  size?: number
  /** Point cible : trace un filet de rappel de (x, y) vers `to`. */
  to?: Point
  /** Leader courbe (Bézier quadratique) au lieu d'une ligne droite. */
  curved?: boolean
  /** Leader en pointillés. Défaut : plein pour une ligne, pointillé si courbe. */
  dashed?: boolean
}

/** Bézier quadratique entre deux points, bombée perpendiculairement. */
function curveLeader(x: number, y: number, to: Point): string {
  const mx = (x + to.x) / 2
  const my = (y + to.y) / 2
  const dx = to.x - x
  const dy = to.y - y
  const len = Math.hypot(dx, dy) || 1
  // Point de contrôle décalé de ~18 % de la longueur, à la normale du segment.
  const off = len * 0.18
  const cx = mx - (dy / len) * off
  const cy = my + (dx / len) * off
  return `M${x} ${y} Q${cx} ${cy} ${to.x} ${to.y}`
}

export function Annotation({ x, y, children, anchor = 'start', size = 12, to, curved = false, dashed }: AnnotationProps) {
  const isDashed = dashed ?? curved
  const dash = isDashed ? '3 3' : undefined
  return (
    <g data-diagram="annotation">
      {to &&
        (curved ? (
          <path
            data-diagram="leader"
            d={curveLeader(x, y, to)}
            fill="none"
            stroke={DIAGRAM.hairlineColor}
            strokeWidth={DIAGRAM.hairlineWidth}
            strokeDasharray={dash}
          />
        ) : (
          <line
            data-diagram="leader"
            x1={x}
            y1={y}
            x2={to.x}
            y2={to.y}
            stroke={DIAGRAM.hairlineColor}
            strokeWidth={DIAGRAM.hairlineWidth}
            strokeDasharray={dash}
          />
        ))}
      {/* Sérif italique (fontTitle), teinte muted — annotation éditoriale. */}
      <text
        data-diagram="label"
        x={x}
        y={y}
        fontFamily={DIAGRAM.fontTitle}
        fill={DIAGRAM.muted}
        fontSize={size}
        fontStyle="italic"
        textAnchor={anchor}
        dominantBaseline="central"
      >
        {children}
      </text>
    </g>
  )
}
