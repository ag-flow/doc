/** Primitives SVG composables (Lot 0) — briques de rendu partagées des
 *  diagrammes. Chaque primitive consomme la géométrie du socle de layout
 *  (Point/Rect/CartesianFrame) et n'utilise QUE les tokens `--diagram-*`.
 *  À rendre dans un <svg> fourni par le composant de diagramme (Lots 1-5). */
export { DIAGRAM } from './svgTokens'

export { Label } from './Label'
export type { LabelProps, LabelVariant, Anchor } from './Label'

export { Node } from './Node'
export type { NodeProps, NodeVariant } from './Node'

export { Edge } from './Edge'
export type { EdgeProps, EdgeVariant } from './Edge'

export { Grid } from './Grid'
export type { GridProps } from './Grid'

export { Annotation } from './Annotation'
export type { AnnotationProps } from './Annotation'

export { Icon } from './icons/Icon'
export type { IconProps } from './icons/Icon'
export { ICON_NAMES } from './icons/iconPaths'
export type { IconName } from './icons/iconPaths'

export { SketchyDefs, sketchy, SKETCHY_FILTER_ID } from './Sketchy'
export type { SketchyDefsProps } from './Sketchy'

export { TerminalFrame } from './Terminal'
export type { TerminalFrameProps } from './Terminal'
