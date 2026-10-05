/** Primitive Label — texte positionné, typé par variante (titre/nœud/mono/muted).
 *  À rendre dans un <svg>. */
import { DIAGRAM } from './svgTokens'

export type LabelVariant = 'title' | 'node' | 'mono' | 'muted'
export type Anchor = 'start' | 'middle' | 'end'

export interface LabelProps {
  x: number
  y: number
  children: string
  variant?: LabelVariant
  anchor?: Anchor
  /** Taille de police (px). Défaut 12. */
  size?: number
  /** Centrage vertical sur y (dominant-baseline central). Défaut true. */
  middle?: boolean
  italic?: boolean
}

const FONT: Record<LabelVariant, string> = {
  title: DIAGRAM.fontTitle,
  node: DIAGRAM.fontNode,
  mono: DIAGRAM.fontMono,
  muted: DIAGRAM.fontMono,
}

// GARDE-FOU accent : jamais de petit texte en accent (3.65:1 < AA). Le texte
// reste en ink ou muted ; l'accent est réservé aux aplats/bordures (Node focal).
const FILL: Record<LabelVariant, string> = {
  title: DIAGRAM.ink,
  node: DIAGRAM.ink,
  mono: DIAGRAM.ink,
  muted: DIAGRAM.muted,
}

export function Label({
  x,
  y,
  children,
  variant = 'node',
  anchor = 'start',
  size = 12,
  middle = true,
  italic = false,
}: LabelProps) {
  return (
    <text
      data-diagram="label"
      x={x}
      y={y}
      fontFamily={FONT[variant]}
      fill={FILL[variant]}
      fontSize={size}
      fontStyle={italic ? 'italic' : undefined}
      textAnchor={anchor}
      dominantBaseline={middle ? 'central' : undefined}
    >
      {children}
    </text>
  )
}
