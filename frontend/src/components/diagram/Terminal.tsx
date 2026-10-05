/** Variante terminal — habillage fenêtre CLI (fond charcoal, barre à trois
 *  pastilles, mono). Îlot sombre volontaire quel que soit le thème.
 *  Les enfants sont posés relativement à l'origine de la zone de contenu. */
import type { ReactNode } from 'react'
import type { Rect } from '../../lib/diagramLayout'
import { DIAGRAM } from './svgTokens'

const BAR_H = 18
const PAD = 10

export interface TerminalFrameProps {
  /** Cadre de la fenêtre. */
  rect: Rect
  /** Titre affiché dans la barre (mono). */
  title?: string
  /** Contenu SVG, coordonnées relatives au coin haut-gauche de la zone utile. */
  children?: ReactNode
  radius?: number | string
}

export function TerminalFrame({ rect, title, children, radius }: TerminalFrameProps) {
  const dotY = rect.y + BAR_H / 2
  return (
    <g data-diagram="terminal">
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={radius ?? DIAGRAM.radius}
        fill={DIAGRAM.terminalBg}
      />
      {/* Barre de titre : séparateur + trois pastilles + titre mono. */}
      <line
        x1={rect.x}
        y1={rect.y + BAR_H}
        x2={rect.x + rect.width}
        y2={rect.y + BAR_H}
        stroke={DIAGRAM.terminalDot}
        strokeWidth="0.5"
      />
      {[0, 1, 2].map((i) => (
        <circle key={i} data-diagram="terminal-dot" cx={rect.x + 10 + i * 7} cy={dotY} r="2" fill={DIAGRAM.terminalDot} />
      ))}
      {title && (
        <text
          x={rect.x + rect.width / 2}
          y={dotY}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily={DIAGRAM.fontMono}
          fontSize="9"
          fill={DIAGRAM.terminalFg}
        >
          {title}
        </text>
      )}
      <g data-diagram="terminal-content" transform={`translate(${rect.x + PAD} ${rect.y + BAR_H + PAD})`}>
        {children}
      </g>
    </g>
  )
}
