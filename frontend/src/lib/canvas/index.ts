/**
 * API publique du canvas de diagramme (épic MLD — F6).
 *
 * C'est la seule porte d'entrée pour un adaptateur (F7). **Aucun type de React
 * Flow ni d'elkjs n'apparaît ici** : c'est la frontière d'abstraction posée par
 * l'étude F1, et la condition pour que le moteur de rendu ou de placement reste
 * remplaçable sans toucher aux appelants ni au format persisté.
 */

export {
  CANVAS_SCHEMA_VERSION,
  DEFAULT_NODE_SIZE,
  emptyCanvas,
  nodeById,
  nodeSize,
  type CanvasDoc,
  type CanvasEdge,
  type CanvasNode,
  type CanvasPort,
  type EdgeEnd,
  type Point,
  type Side,
  type Size,
  type Viewport,
} from './model'

export { anchorPoint, sidesFor, type Anchor, type AnchorContext } from './anchor'
export { orthogonalRoute, simplify, toSvgPath, STUB } from './route'
export { detailFor, portsVisibleAt, DETAIL_THRESHOLDS, type DetailLevel } from './detail'
export { autoArrange } from './layout'
export { Canvas, type CanvasProps } from '../../components/canvas/Canvas'
