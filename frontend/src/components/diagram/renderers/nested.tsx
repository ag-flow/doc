/** Rendu `df-diagram type="nested"` — hiérarchie par containment (boîtes
 *  imbriquées). L'indentation du corps donne l'emboîtement. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseOutline, type OutlineNode } from '../../../lib/blockCodecs/outline'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 320
const PAD = 8
const PADX = 8
const PADY = 8
const HEADER = 20
const LEAF_H = 26
const GAP = 6

/** Hauteur d'un nœud (indépendante de la largeur). */
function measure(node: OutlineNode): number {
  if (node.children.length === 0) return LEAF_H
  const inner = node.children.reduce((s, c) => s + measure(c), 0) + GAP * (node.children.length - 1)
  return HEADER + inner + PADY
}

/** Émet les rectangles imbriqués d'un nœud (conteneur derrière ses enfants). */
function renderNode(node: OutlineNode, x: number, y: number, width: number, key: string): ReactNode {
  const h = measure(node)
  const leaf = node.children.length === 0
  const box = (
    <rect
      x={x}
      y={y}
      width={width}
      height={h}
      rx={DIAGRAM.radius}
      fill={DIAGRAM.paper2}
      stroke={DIAGRAM.hairlineColor}
      strokeWidth={DIAGRAM.hairlineWidth}
    />
  )
  const label = leaf ? (
    <Label x={x + width / 2} y={y + h / 2} anchor="middle" variant="node" size={11}>
      {node.label}
    </Label>
  ) : (
    <Label x={x + PADX} y={y + HEADER / 2 + 2} anchor="start" variant="node" size={11}>
      {node.label}
    </Label>
  )
  const children: ReactNode[] = []
  let cy = y + HEADER
  node.children.forEach((child, i) => {
    children.push(renderNode(child, x + PADX, cy, width - 2 * PADX, `${key}-${i}`))
    cy += measure(child) + GAP
  })
  return (
    <g key={key} data-diagram="nested-node">
      {box}
      {label}
      {children}
    </g>
  )
}

export function NestedDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const { roots, ignored } = parseOutline(body)
  if (roots.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const width = W - 2 * PAD
  let y = PAD
  const groups: ReactNode[] = []
  roots.forEach((root, i) => {
    groups.push(renderNode(root, PAD, y, width, `r${i}`))
    y += measure(root) + GAP
  })
  const H = y - GAP + PAD

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 480 }} role="img">
        {groups}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
