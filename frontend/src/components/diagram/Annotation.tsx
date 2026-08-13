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
}

export function Annotation({ x, y, children, anchor = 'start', size = 12, to }: AnnotationProps) {
  return (
    <g data-diagram="annotation">
      {to && (
        <line
          data-diagram="leader"
          x1={x}
          y1={y}
          x2={to.x}
          y2={to.y}
          stroke={DIAGRAM.hairlineColor}
          strokeWidth={DIAGRAM.hairlineWidth}
        />
      )}
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
