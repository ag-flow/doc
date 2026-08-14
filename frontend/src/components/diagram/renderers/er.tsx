/** Rendu `df-diagram type="er"` — entités (titre + champs) et relations.
 *  Corps : une ligne non indentée = entité ; lignes indentées = ses champs ;
 *  une ligne avec `->` = relation entre entités. */
import type { ReactNode } from 'react'
import type { Rect } from '../../../lib/diagramLayout'
import { Label } from '../Label'
import { Node } from '../Node'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const PAD = 8
const EW = 118
const TITLE_H = 22
const FIELD_H = 18
const HGAP = 30
const VGAP = 24

interface Entity {
  id: string
  fields: string[]
}

function parseEr(body: string): { entities: Entity[]; relations: Array<[string, string]> } {
  const entities: Entity[] = []
  const relations: Array<[string, string]> = []
  let current: Entity | null = null
  for (const raw of body.split('\n')) {
    if (raw.trim().length === 0) continue
    if (raw.includes('->')) {
      const [a, b] = raw.split('->').map((s) => s.trim())
      if (a && b) relations.push([a, b])
      continue
    }
    const indented = /^[ \t]/.test(raw)
    if (indented && current) {
      current.fields.push(raw.trim())
    } else {
      current = { id: raw.trim(), fields: [] }
      entities.push(current)
    }
  }
  return { entities, relations }
}

export function ErDiagram({ body, svgRef }: RendererProps) {
  const { entities, relations } = parseEr(body)
  if (entities.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const cols = Math.min(3, entities.length)
  const rows = Math.ceil(entities.length / cols)
  const entH = (e: Entity) => TITLE_H + e.fields.length * FIELD_H
  const maxH = Math.max(...entities.map(entH))
  const rectOf = (i: number): Rect => ({
    x: PAD + (i % cols) * (EW + HGAP),
    y: PAD + Math.floor(i / cols) * (maxH + VGAP),
    width: EW,
    height: entH(entities[i]),
  })
  const byId = new Map(entities.map((e, i) => [e.id, i]))
  const W = PAD + cols * (EW + HGAP) - HGAP + PAD
  const H = PAD + rows * (maxH + VGAP) - VGAP + PAD

  const relEls: ReactNode[] = relations.map(([a, b], i) => {
    const ia = byId.get(a)
    const ib = byId.get(b)
    if (ia === undefined || ib === undefined) return null
    const ra = rectOf(ia)
    const rb = rectOf(ib)
    return (
      <line
        key={`r${i}`}
        x1={ra.x + ra.width / 2}
        y1={ra.y + ra.height / 2}
        x2={rb.x + rb.width / 2}
        y2={rb.y + rb.height / 2}
        stroke={DIAGRAM.hairlineColor}
        strokeWidth={DIAGRAM.hairlineWidth}
      />
    )
  })

  const entEls: ReactNode[] = entities.map((e, i) => {
    const r = rectOf(i)
    return (
      <g key={`e${i}`} data-diagram="entity">
        <Node rect={r} />
        {/* Titre + séparateur. */}
        <Label x={r.x + r.width / 2} y={r.y + TITLE_H / 2} anchor="middle" variant="node" size={11}>
          {e.id}
        </Label>
        <line x1={r.x} y1={r.y + TITLE_H} x2={r.x + r.width} y2={r.y + TITLE_H} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
        {e.fields.map((f, fi) => (
          <Label key={fi} x={r.x + 8} y={r.y + TITLE_H + fi * FIELD_H + FIELD_H / 2} anchor="start" variant="mono" size={9}>
            {f}
          </Label>
        ))}
      </g>
    )
  })

  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 460 }} role="img">
      {relEls}
      {entEls}
    </svg>
  )
}
