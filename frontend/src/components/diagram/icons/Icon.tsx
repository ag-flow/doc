/** Primitive Icon — glyphe monochrome `currentColor`, posable en SVG (x/y) ou
 *  en flux HTML. Hérite de la couleur du contexte (mettre `color` sur le parent,
 *  ex. `color: var(--diagram-ink)`). */
import { ICONS, type IconName } from './iconPaths'

export interface IconProps {
  name: IconName
  /** Côté du carré de rendu (px). Défaut 24. */
  size?: number
  /** Position (contexte SVG). Omis en flux HTML. */
  x?: number
  y?: number
  /** Épaisseur du trait. Défaut 1.75. */
  strokeWidth?: number
  /** Libellé accessible. Défaut : le nom. */
  title?: string
}

export function Icon({ name, size = 24, x, y, strokeWidth = 1.75, title }: IconProps) {
  return (
    <svg
      data-diagram="icon"
      data-icon={name}
      x={x}
      y={y}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={title ?? name}
    >
      {ICONS[name]}
    </svg>
  )
}
