import { describe, it, expect } from 'vitest'
import { layeredGraph, type GraphNode, type GraphEdge } from '../lib/diagramLayout'
import { parseGraph } from '../lib/blockCodecs/graphSpec'

describe('layeredGraph — couches par profondeur', () => {
  const nodes: GraphNode[] = [
    { id: 'A', label: 'A' },
    { id: 'B', label: 'B' },
    { id: 'C', label: 'C' },
  ]
  const edges: GraphEdge[] = [
    { from: 'A', to: 'B' },
    { from: 'B', to: 'C' },
  ]

  it('chaîne A→B→C = 3 couches ordonnées', () => {
    const g = layeredGraph(nodes, edges, { dir: 'LR' })
    expect(g.layers.map((l) => l.length)).toEqual([1, 1, 1])
    const ax = g.placed.get('A')!.x
    const bx = g.placed.get('B')!.x
    const cx = g.placed.get('C')!.x
    expect(ax).toBeLessThan(bx)
    expect(bx).toBeLessThan(cx)
  })

  it('LR et TB échangent les axes', () => {
    const lr = layeredGraph(nodes, edges, { dir: 'LR' })
    const tb = layeredGraph(nodes, edges, { dir: 'TB' })
    // LR : progression en x ; TB : progression en y.
    expect(tb.placed.get('C')!.y).toBeGreaterThan(tb.placed.get('A')!.y)
    expect(lr.width).toBeGreaterThan(lr.height)
    expect(tb.height).toBeGreaterThan(tb.width)
  })
})

describe('layeredGraph — couches par groupe', () => {
  it('un groupe = une couche (ordre de première apparition)', () => {
    const nodes: GraphNode[] = [
      { id: 'raw', label: 'Raw', group: 'Bronze' },
      { id: 'clean', label: 'Clean', group: 'Silver' },
      { id: 'agg', label: 'Agg', group: 'Silver' },
    ]
    const g = layeredGraph(nodes, edges2([['raw', 'clean']]), { dir: 'LR' })
    expect(g.layers.length).toBe(2)
    expect(g.layers[0]).toEqual(['raw'])
    expect(g.layers[1].sort()).toEqual(['agg', 'clean'])
  })
})

describe('layeredGraph — robustesse cycle', () => {
  it('un cycle A↔B ne boucle pas', () => {
    const nodes: GraphNode[] = [
      { id: 'A', label: 'A' },
      { id: 'B', label: 'B' },
    ]
    const g = layeredGraph(nodes, edges2([['A', 'B'], ['B', 'A']]), {})
    expect(g.placed.size).toBe(2)
  })
})

function edges2(pairs: Array<[string, string]>): GraphEdge[] {
  return pairs.map(([from, to]) => ({ from, to }))
}

describe('parseGraph', () => {
  it('les arêtes créent les nœuds ; label d’arête via |', () => {
    const g = parseGraph('A -> B | appelle')
    expect(g.nodes.map((n) => n.id).sort()).toEqual(['A', 'B'])
    expect(g.edges).toEqual([{ from: 'A', to: 'B', label: 'appelle' }])
  })

  it('déclaration de nœud : id | label | groupe', () => {
    const g = parseGraph('api | API Gateway | Coeur\napi -> db')
    const api = g.nodes.find((n) => n.id === 'api')!
    expect(api.label).toBe('API Gateway')
    expect(api.group).toBe('Coeur')
    // db créé à la volée, label = id.
    expect(g.nodes.find((n) => n.id === 'db')!.label).toBe('db')
  })

  it('compte les lignes ignorées (arête sans cible)', () => {
    const g = parseGraph('A ->\nB')
    expect(g.ignored).toBe(1)
    expect(g.nodes.map((n) => n.id)).toContain('B')
  })
})
