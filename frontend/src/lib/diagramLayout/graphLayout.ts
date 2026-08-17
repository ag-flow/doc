/** Layout en couches d'un graphe orienté (données → géométrie).
 *  Base des diagrammes graphe/flux (Architecture, Data flow, Medallion…).
 *  Deux modes de superposition :
 *   - par groupe : si TOUS les nœuds ont un `group`, une couche = un groupe
 *     (ordre de première apparition) — pour les tiers/étages (Medallion…) ;
 *   - par profondeur sinon : longest-path depuis les sources (in-degré 0),
 *     les arêtes de retour d'un cycle étant écartées du calcul. */
import type { Rect } from './types'

export interface GraphNode {
  id: string
  label: string
  group?: string
}

export interface GraphEdge {
  from: string
  to: string
  label?: string
}

export interface LayeredOptions {
  /** Dimensions d'un nœud. */
  nodeW?: number
  nodeH?: number
  /** Écart entre couches (axe principal) et entre nœuds d'une couche (axe croisé). */
  gapMain?: number
  gapCross?: number
  /** Sens du flux : 'LR' (couches en colonnes) ou 'TB' (couches en lignes). */
  dir?: 'LR' | 'TB'
  pad?: number
}

export interface LayeredGraph {
  /** Rectangle de chaque nœud, par id. */
  placed: Map<string, Rect>
  /** Ids par couche, dans l'ordre de placement. */
  layers: string[][]
  width: number
  height: number
}

/** Arêtes sortantes de chaque nœud, dans l'ordre de déclaration. Self-loops et
 *  extrémités inconnues exclus : ils ne définissent aucun niveau. */
function adjacency(nodes: GraphNode[], edges: GraphEdge[]): Map<string, GraphEdge[]> {
  const known = new Set(nodes.map((n) => n.id))
  const out = new Map<string, GraphEdge[]>(nodes.map((n) => [n.id, []]))
  for (const e of edges) {
    if (e.from === e.to || !known.has(e.from) || !known.has(e.to)) continue
    out.get(e.from)!.push(e)
  }
  return out
}

/** Arêtes arrière d'un DFS (cible encore en cours d'exploration). Les retirer
 *  rend le graphe acyclique : tout cycle contient au moins une arête arrière. */
function backEdges(nodes: GraphNode[], out: Map<string, GraphEdge[]>): Set<GraphEdge> {
  const back = new Set<GraphEdge>()
  const open = new Set<string>()
  const done = new Set<string>()
  for (const root of nodes) {
    if (done.has(root.id)) continue
    const stack: Array<{ id: string; next: number }> = [{ id: root.id, next: 0 }]
    open.add(root.id)
    while (stack.length > 0) {
      const top = stack[stack.length - 1]
      const adj = out.get(top.id) ?? []
      if (top.next >= adj.length) {
        open.delete(top.id)
        done.add(top.id)
        stack.pop()
        continue
      }
      const e = adj[top.next++]
      if (open.has(e.to)) back.add(e)
      else if (!done.has(e.to)) {
        open.add(e.to)
        stack.push({ id: e.to, next: 0 })
      }
    }
  }
  return back
}

/** Plus long chemin (Kahn) sur le graphe privé de ses arêtes arrière : les
 *  sources sont en couche 0, chaque nœud une couche après son prédécesseur le
 *  plus profond. Sur un DAG le résultat est identique à la relaxation naïve. */
function longestPath(nodes: GraphNode[], out: Map<string, GraphEdge[]>, back: Set<GraphEdge>): Map<string, number> {
  const layer = new Map<string, number>(nodes.map((n) => [n.id, 0]))
  const indeg = new Map<string, number>(nodes.map((n) => [n.id, 0]))
  const forward = (id: string): GraphEdge[] => (out.get(id) ?? []).filter((e) => !back.has(e))
  for (const n of nodes) for (const e of forward(n.id)) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)
  const queue = nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
  for (let i = 0; i < queue.length; i++) {
    for (const e of forward(queue[i])) {
      layer.set(e.to, Math.max(layer.get(e.to) ?? 0, (layer.get(queue[i]) ?? 0) + 1))
      const rest = (indeg.get(e.to) ?? 0) - 1
      indeg.set(e.to, rest)
      if (rest === 0) queue.push(e.to)
    }
  }
  return layer
}

/** Indice de couche de chaque nœud. */
function assignLayers(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const groupMode = nodes.length > 0 && nodes.every((n) => n.group !== undefined && n.group !== '')
  if (groupMode) {
    const layer = new Map<string, number>()
    const order: string[] = []
    for (const n of nodes) if (!order.includes(n.group!)) order.push(n.group!)
    for (const n of nodes) layer.set(n.id, order.indexOf(n.group!))
    return layer
  }
  const out = adjacency(nodes, edges)
  return longestPath(nodes, out, backEdges(nodes, out))
}

/** Positionne les nœuds en couches. Chaque couche est centrée sur l'axe croisé. */
export function layeredGraph(nodes: GraphNode[], edges: GraphEdge[], opts: LayeredOptions = {}): LayeredGraph {
  const nodeW = opts.nodeW ?? 96
  const nodeH = opts.nodeH ?? 34
  const gapMain = opts.gapMain ?? 48
  const gapCross = opts.gapCross ?? 16
  const pad = opts.pad ?? 10
  const dir = opts.dir ?? 'LR'

  const layerOf = assignLayers(nodes, edges)
  const maxLayer = Math.max(0, ...Array.from(layerOf.values()))
  const layers: string[][] = Array.from({ length: maxLayer + 1 }, () => [])
  for (const n of nodes) layers[layerOf.get(n.id) ?? 0].push(n.id)

  // Axe principal = celui des couches ; axe croisé = le placement dans la couche.
  const lr = dir === 'LR'
  const nodeMain = lr ? nodeW : nodeH
  const nodeCross = lr ? nodeH : nodeW
  const crossStep = nodeCross + gapCross
  const maxCount = Math.max(1, ...layers.map((l) => l.length))
  const crossExtent = maxCount * crossStep - gapCross

  const placed = new Map<string, Rect>()
  layers.forEach((ids, li) => {
    const main = pad + li * (nodeMain + gapMain)
    const layerLen = ids.length * crossStep - gapCross
    const start = pad + (crossExtent - layerLen) / 2
    ids.forEach((id, i) => {
      const cross = start + i * crossStep
      const rect: Rect = lr
        ? { x: main, y: cross, width: nodeW, height: nodeH }
        : { x: cross, y: main, width: nodeW, height: nodeH }
      placed.set(id, rect)
    })
  })

  const mainTotal = pad * 2 + (maxLayer + 1) * nodeMain + maxLayer * gapMain
  const crossTotal = pad * 2 + crossExtent
  return {
    placed,
    layers,
    width: lr ? mainTotal : crossTotal,
    height: lr ? crossTotal : mainTotal,
  }
}
