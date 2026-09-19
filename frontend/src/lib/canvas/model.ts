/**
 * Modèle sérialisable du canvas de diagramme (épic MLD — F6).
 *
 * Ce fichier EST le contrat : c'est lui qui part en base comme corps d'un
 * document, et c'est la seule chose qu'un adaptateur (F7) doit connaître.
 *
 * **Frontière d'abstraction** — condition posée par l'étude F1 : ni React Flow
 * ni elkjs n'apparaissent ici, ni dans aucune signature publique de `lib/canvas`.
 * Le moteur de rendu et le moteur de placement doivent rester remplaçables sans
 * toucher ni au format persisté ni aux appelants.
 *
 * Le canvas est **générique** : il ne sait rien des modèles de données. Un nœud
 * a des ports et une étiquette, pas des « colonnes » ; c'est l'adaptateur qui
 * traduit une table en nœud.
 */

/** Version du format persisté. Incrémentée à tout changement non rétro-compatible. */
export const CANVAS_SCHEMA_VERSION = 1

export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

/** Côté d'une boîte où un lien peut s'accrocher. */
export type Side = 'left' | 'right' | 'top' | 'bottom'

/**
 * Point d'accroche d'un lien sur un nœud.
 *
 * Un port correspond à une ligne du nœud (un champ, dans le cas MLD) : c'est ce
 * qui permet l'ancrage fin. `offset` est la distance verticale depuis le haut de
 * la boîte, en coordonnées du nœud — le canvas ne sait pas ce qu'est un champ,
 * il sait seulement à quelle hauteur accrocher.
 */
export interface CanvasPort {
  id: string
  /** Distance verticale depuis le haut du nœud, en pixels. */
  offset: number
  label?: string
}

export interface CanvasNode {
  id: string
  /** Famille de nœud, interprétée par l'adaptateur (ex. `table`). */
  kind: string
  position: Point
  size?: Size
  ports?: CanvasPort[]
  /** Repliée : les ports ne sont plus visibles, les liens dégradent vers le bord. */
  collapsed?: boolean
  /** Charge utile libre, opaque au canvas — c'est l'affaire de l'adaptateur. */
  data?: Record<string, unknown>
}

/** Extrémité d'un lien : un nœud, et éventuellement un port précis. */
export interface EdgeEnd {
  node: string
  /** Absent, inconnu ou masqué (nœud replié) → ancrage dégradé sur le bord. */
  port?: string
}

export interface CanvasEdge {
  id: string
  source: EdgeEnd
  target: EdgeEnd
  /** Famille de lien, interprétée par l'adaptateur (ex. une cardinalité). */
  kind?: string
  label?: string
  /**
   * Coudes imposés par l'utilisateur, en coordonnées ABSOLUES du canvas.
   *
   * Absent = le tracé est calculé (routage orthogonal automatique). Présent =
   * l'utilisateur a déplacé le lien à la main et son choix prime : on ne
   * recalcule pas par-dessus une intention explicite.
   */
  waypoints?: Point[]
}

export interface Viewport extends Point {
  zoom: number
}

/** Document de canvas — ce qui est persisté tel quel. */
export interface CanvasDoc {
  schemaVersion: number
  viewport?: Viewport
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

export function emptyCanvas(): CanvasDoc {
  return { schemaVersion: CANVAS_SCHEMA_VERSION, nodes: [], edges: [] }
}

/** Dimensions retenues quand un nœud n'en porte pas. */
export const DEFAULT_NODE_SIZE: Size = { width: 220, height: 80 }

export function nodeSize(node: CanvasNode): Size {
  return node.size ?? DEFAULT_NODE_SIZE
}

export function nodeById(doc: CanvasDoc, id: string): CanvasNode | undefined {
  return doc.nodes.find((n) => n.id === id)
}
