/** Contrat commun des rendus de `df-diagram`. Chaque rendu est un composant
 *  autonome : il parse le corps, gère son repli et ses badges, et rend un
 *  <svg ref> (pour l'export SVG du BlockFrame). */
import type { RefObject } from 'react'

export interface RendererProps {
  /** Corps brut de la fence (sans les ```). */
  body: string
  /** Attributs parsés de la fence (type, variant, title…). */
  conf: Record<string, string>
  /** Ref du <svg> racine, pour le téléchargement SVG. */
  svgRef: RefObject<SVGSVGElement | null>
}
