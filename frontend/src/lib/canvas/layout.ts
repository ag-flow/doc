/**
 * Placement automatique des nœuds (épic MLD — F6).
 *
 * elkjs est **confiné à ce fichier** : c'est la frontière d'abstraction posée par
 * l'étude F1. Sa signature ne parle que de `CanvasDoc`, donc remplacer le moteur
 * de placement ne toucherait ni le format persisté, ni les composants, ni les
 * appelants.
 *
 * Répartition des rôles, volontairement nette :
 *   - **elk arrange** — il décide où poser les boîtes ;
 *   - **`route.ts` dessine** — il décide de la forme des liens.
 * Le cadrage exige que le tracé soit une fonction isolée de nous ; on ne délègue
 * donc pas le routage à elk, seulement le placement.
 */

import type { CanvasDoc } from './model'
import { nodeSize } from './model'

/**
 * elkjs pèse près d'un mégaoctet : il est chargé à la PREMIÈRE demande de
 * ré-arrangement, pas au chargement de l'application. Un utilisateur qui ne lit
 * que du markdown ne doit pas payer le moteur de placement d'un diagramme.
 *
 * L'import est mémorisé : les ré-arrangements suivants sont immédiats.
 */
let elkPromise: Promise<{ layout: (g: unknown) => Promise<ElkResult> }> | null = null

interface ElkResult {
  children?: Array<{ id: string; x?: number; y?: number }>
}

async function engine() {
  if (!elkPromise) {
    elkPromise = import('elkjs/lib/elk.bundled.js').then(
      (m) => new (m.default as new () => { layout: (g: unknown) => Promise<ElkResult> })(),
    )
  }
  return elkPromise
}

/** Options de placement : couches orientées gauche→droite, comme un MLD se lit. */
const LAYOUT_OPTIONS: Record<string, string> = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.layered.spacing.nodeNodeBetweenLayers': '120',
  'elk.spacing.nodeNode': '60',
  'elk.edgeRouting': 'ORTHOGONAL',
}

/**
 * Replace les nœuds. Rend un NOUVEAU document ; l'entrée n'est pas modifiée.
 *
 * Les coudes imposés par l'utilisateur (`waypoints`) sont **effacés** : ils sont
 * exprimés en coordonnées absolues, donc ils n'ont plus de sens une fois les
 * boîtes déplacées. C'est un arbitrage assumé — un ré-arrangement est une
 * demande explicite de tout réorganiser.
 */
export async function autoArrange(doc: CanvasDoc): Promise<CanvasDoc> {
  if (doc.nodes.length === 0) return doc

  const graph = {
    id: 'root',
    layoutOptions: LAYOUT_OPTIONS,
    children: doc.nodes.map((n) => ({ id: n.id, ...nodeSize(n) })),
    edges: doc.edges.map((e) => ({
      id: e.id,
      sources: [e.source.node],
      targets: [e.target.node],
    })),
  }

  const laid = await (await engine()).layout(graph)
  const placed = new Map(
    (laid.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]),
  )

  return {
    ...doc,
    nodes: doc.nodes.map((n) => ({ ...n, position: placed.get(n.id) ?? n.position })),
    edges: doc.edges.map(({ waypoints: _dropped, ...rest }) => rest),
  }
}
