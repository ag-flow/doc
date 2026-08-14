/** Layout en couches d'un graphe orienté (données → géométrie).
 *  Base des diagrammes graphe/flux (Architecture, Data flow, Medallion…).
 *  Deux modes de superposition :
 *   - par groupe : si TOUS les nœuds ont un `group`, une couche = un groupe
 *     (ordre de première apparition) — pour les tiers/étages (Medallion…) ;
 *   - par profondeur sinon : longest-path depuis les sources (in-degré 0). */
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

/** Indice de couche de chaque nœud. */
function assignLayers(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const layer = new Map<string, number>()
  const groupMode = nodes.length > 0 && nodes.every((n) => n.group !== undefined && n.group !== '')
  if (groupMode) {
    const order: string[] = []
    for (const n of nodes) if (!order.includes(n.group!)) order.push(n.group!)
    for (const n of nodes) layer.set(n.id, order.indexOf(n.group!))
    return layer
  }
  // Longest-path : source = in-degré 0 → couche 0, puis relaxation bornée.
  const indeg = new Map<string, number>(nodes.map((n) => [n.id, 0]))
  for (const e of edges) if (indeg.has(e.to)) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)
  for (const n of nodes) layer.set(n.id, 0)
  // Au plus |nodes| passes : converge sur un DAG, borné sur un cycle.
  for (let pass = 0; pass < nodes.length; pass++) {
    let changed = false
    for (const e of edges) {
      // Un self-loop (A→A) ne définit pas de niveau : il gonflerait la couche.
      if (e.from === e.to) continue
      if (!layer.has(e.from) || !layer.has(e.to)) continue
      const want = (layer.get(e.from) ?? 0) + 1
      if (want > (layer.get(e.to) ?? 0)) {
        layer.set(e.to, want)
        changed = true
      }
    }
    if (!changed) break
  }
  return layer
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
