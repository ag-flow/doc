/** Socle de layout algorithmique partagé (Lot 0) — point d'entrée unique.
 *
 *  Calcul géométrique réutilisable entre types de diagramme des Lots 1-5 :
 *  échelles, repère cartésien, placement radial, grille de quadrants, bandes.
 *  Ce socle ne fournit QUE le calcul (données → géométrie), jamais le rendu. */
export type { Point, Rect, Extent, Padding } from './types'
export { resolvePadding } from './types'

export type { Scale } from './scales'
export { linearScale, timeScale, niceTicks, extentOf, timeExtent } from './scales'

export type { CartesianOptions, CartesianFrame } from './cartesian'
export { cartesianFrame } from './cartesian'

export type { RadialOptions } from './radial'
export { radialPoint, radialPoints, radialAngle } from './radial'

export type { QuadrantOptions, QuadrantGrid } from './quadrant'
export { quadrantGrid } from './quadrant'

export type { LanesOptions, Lanes } from './lanes'
export { lanes } from './lanes'

export type { GraphNode, GraphEdge, LayeredOptions, LayeredGraph } from './graphLayout'
export { layeredGraph } from './graphLayout'
