/** Primitive Grid — lignes de repère + axes + graduations d'un repère cartésien
 *  (consomme un CartesianFrame du socle de layout). À rendre dans un <svg>. */
import type { CartesianFrame } from '../../lib/diagramLayout'
import { Label } from './Label'
import { DIAGRAM } from './svgTokens'

export interface GridProps {
  frame: CartesianFrame
  /** Lignes de repère verticales (aux graduations X). Défaut true. */
  vertical?: boolean
  /** Lignes de repère horizontales (aux graduations Y). Défaut true. */
  horizontal?: boolean
  /** Axes X (bas) et Y (gauche) en encre pleine. Défaut true. */
  axes?: boolean
  /** Libellés de graduations (mono/muted). Défaut false. */
  labels?: boolean
  /** Formateur des libellés d'axe. Défaut : nombre compact. */
  format?: (value: number) => string
}

const defaultFormat = (v: number): string => (Number.isInteger(v) ? String(v) : v.toFixed(1))

export function Grid({
  frame,
  vertical = true,
  horizontal = true,
  axes = true,
  labels = false,
  format = defaultFormat,
}: GridProps) {
  const { plot, x, y, xTicks, yTicks } = frame
  const left = plot.x
  const right = plot.x + plot.width
  const top = plot.y
  const bottom = plot.y + plot.height
  return (
    <g data-diagram="grid">
      {vertical &&
        xTicks.map((t) => (
          <line
            key={`vx-${t}`}
            data-diagram="gridline"
            x1={x(t)}
            y1={top}
            x2={x(t)}
            y2={bottom}
            stroke={DIAGRAM.hairlineColor}
            strokeWidth={DIAGRAM.hairlineWidth}
          />
        ))}
      {horizontal &&
        yTicks.map((t) => (
          <line
            key={`hy-${t}`}
            data-diagram="gridline"
            x1={left}
            y1={y(t)}
            x2={right}
            y2={y(t)}
            stroke={DIAGRAM.hairlineColor}
            strokeWidth={DIAGRAM.hairlineWidth}
          />
        ))}
      {axes && (
        <>
          <line data-diagram="axis-x" x1={left} y1={bottom} x2={right} y2={bottom} stroke={DIAGRAM.ink} strokeWidth={DIAGRAM.hairlineWidth} />
          <line data-diagram="axis-y" x1={left} y1={top} x2={left} y2={bottom} stroke={DIAGRAM.ink} strokeWidth={DIAGRAM.hairlineWidth} />
        </>
      )}
      {labels &&
        xTicks.map((t) => (
          <Label key={`lx-${t}`} x={x(t)} y={bottom + 10} anchor="middle" variant="muted" size={9}>
            {format(t)}
          </Label>
        ))}
      {labels &&
        yTicks.map((t) => (
          <Label key={`ly-${t}`} x={left - 4} y={y(t)} anchor="end" variant="muted" size={9}>
            {format(t)}
          </Label>
        ))}
    </g>
  )
}
