/** Primitive Node — boîte (rect arrondi) posée sur un Rect du socle de layout,
 *  avec label optionnel (+ sublabel mono). Variante `focal` = bordure accent
 *  (réservée à 1-2 nœuds). À rendre dans un <svg>. */
import type { Rect } from '../../lib/diagramLayout'
import { Label } from './Label'
import { DIAGRAM } from './svgTokens'

export type NodeVariant = 'default' | 'focal'

export interface NodeProps {
  rect: Rect
  label?: string
  /** Sous-label technique (rendu en mono/muted sous le label). */
  sublabel?: string
  variant?: NodeVariant
  /** Rayon des coins (px). Défaut : token --diagram-radius. */
  radius?: number | string
}

export function Node({ rect, label, sublabel, variant = 'default', radius }: NodeProps) {
  const focal = variant === 'focal'
  const cx = rect.x + rect.width / 2
  const cy = rect.y + rect.height / 2
  return (
    <g data-diagram="node" data-variant={variant}>
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={radius ?? DIAGRAM.radius}
        fill={DIAGRAM.paper2}
        stroke={focal ? DIAGRAM.accent : DIAGRAM.hairlineColor}
        strokeWidth={DIAGRAM.hairlineWidth}
      />
      {label && (
        <Label x={cx} y={sublabel ? cy - 6 : cy} anchor="middle" variant="node" size={12}>
          {label}
        </Label>
      )}
      {sublabel && (
        <Label x={cx} y={cy + 10} anchor="middle" variant="muted" size={9}>
          {sublabel}
        </Label>
      )}
    </g>
  )
}
