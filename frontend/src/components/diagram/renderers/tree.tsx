/** Rendu `df-diagram type="tree"` — arbre parent→enfants (node-link, haut→bas).
 *  L'indentation du corps donne la relation parent/enfant. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseOutline, maxDepth, type OutlineNode } from '../../../lib/blockCodecs/outline'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Edge } from '../Edge'
import { Node } from '../Node'
import type { RendererProps } from './types'

const PAD = 10
const NODE_W = 92
const NODE_H = 26
const H_GAP = 16
const LEVEL_H = 54

interface Placed {
  node: OutlineNode
  cx: number
  y: number
}

/** Assigne (cx, y) à chaque nœud : feuilles en créneaux, parents centrés. */
function layoutForest(roots: OutlineNode[]): { placed: Placed[]; edges: Array<[Placed, Placed]> } {
  const placed: Placed[] = []
  const edges: Array<[Placed, Placed]> = []
  let slot = 0

  function walk(node: OutlineNode, depth: number): Placed {
    const y = PAD + depth * LEVEL_H
    let cx: number
    if (node.children.length === 0) {
      cx = PAD + slot * (NODE_W + H_GAP) + NODE_W / 2
      slot++
    } else {
      const kids = node.children.map((c) => walk(c, depth + 1))
      cx = kids.reduce((s, k) => s + k.cx, 0) / kids.length
      for (const k of kids) edges.push([{ node, cx, y }, k])
    }
    const self: Placed = { node, cx, y }
    placed.push(self)
    return self
  }

  for (const root of roots) walk(root, 0)
  return { placed, edges }
}

export function TreeDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const { roots, ignored } = parseOutline(body)
  if (roots.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const { placed, edges } = layoutForest(roots)
  const W = Math.max(...placed.map((p) => p.cx + NODE_W / 2)) + PAD
  const H = PAD + maxDepth(roots) * LEVEL_H + NODE_H + PAD

  const nodeEls: ReactNode[] = placed.map((p, i) => (
    <Node key={`n${i}`} rect={{ x: p.cx - NODE_W / 2, y: p.y, width: NODE_W, height: NODE_H }} label={p.node.label} />
  ))
  const edgeEls: ReactNode[] = edges.map(([parent, child], i) => (
    <Edge
      key={`e${i}`}
      from={{ x: parent.cx, y: parent.y + NODE_H }}
      to={{ x: child.cx, y: child.y }}
      variant="orthogonal"
    />
  ))

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 480 }} role="img">
        {/* Arêtes derrière les nœuds. */}
        {edgeEls}
        {nodeEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
