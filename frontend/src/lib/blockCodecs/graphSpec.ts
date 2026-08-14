/**
 * Grammaire `graph` — nœuds + arêtes, pour les diagrammes graphe/flux (Lot 2).
 *
 * Une ligne contenant `->` est une ARÊTE : `A -> B` ou `A -> B | libellé`.
 * Sinon c'est une déclaration de NŒUD : `id | Label | groupe?` (les champs
 * absents : label = id, pas de groupe). Un nœud cité dans une arête mais non
 * déclaré est créé à la volée (label = id). Lignes vides ignorées.
 */
import type { GraphEdge, GraphNode } from '../diagramLayout'

export interface ParsedGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  ignored: number
}

/** Découpe sur `|` non échappé, dé-échappe `\|`, trim. */
function fields(text: string): string[] {
  const out: string[] = []
  let cur = ''
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\\' && text[i + 1] === '|') {
      cur += '|'
      i++
    } else if (text[i] === '|') {
      out.push(cur)
      cur = ''
    } else cur += text[i]
  }
  out.push(cur)
  return out.map((f) => f.trim())
}

export function parseGraph(body: string): ParsedGraph {
  const nodes = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []
  let ignored = 0

  const ensure = (id: string): void => {
    if (id.length > 0 && !nodes.has(id)) nodes.set(id, { id, label: id })
  }

  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (line.length === 0) continue

    if (line.includes('->')) {
      const arrow = line.indexOf('->')
      const from = line.slice(0, arrow).trim()
      const rest = line.slice(arrow + 2)
      const [target, label] = fields(rest)
      if (from.length === 0 || !target || target.length === 0) {
        ignored++
        continue
      }
      ensure(from)
      ensure(target)
      edges.push({ from, to: target, label: label || undefined })
      continue
    }

    const [id, label, group] = fields(line)
    if (!id || id.length === 0) {
      ignored++
      continue
    }
    // Une re-déclaration enrichit le label/groupe d'un nœud déjà créé par arête.
    nodes.set(id, { id, label: label || id, group: group || undefined })
  }

  return { nodes: Array.from(nodes.values()), edges, ignored }
}
