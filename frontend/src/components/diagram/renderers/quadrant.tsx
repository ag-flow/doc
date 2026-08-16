/** Rendu `df-diagram type="quadrant"` (alias `consultant`) — positionnement à
 *  deux axes. Corps : `label | x | y`. Attributs : `xmax`/`ymax` (défaut 10),
 *  `xlabel`/`ylabel`, `quadrants="tl,tr,bl,br"` (libellés de cellules). */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { quadrantGrid } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 320
const H = 300
const PAD = 30

function num(raw: string, fallback: number): number {
  const trimmed = (raw ?? '').trim()
  if (trimmed === '') return fallback
  const n = Number(trimmed.replace(',', '.'))
  return Number.isFinite(n) ? n : fallback
}

export function QuadrantDiagram({ body, conf, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 3 })
  const items = parsed.rows
    .filter((r) => r[0].length > 0)
    .map((r) => ({ label: r[0], x: num(r[1], NaN), y: num(r[2], NaN) }))
  const valid = items.filter((i) => !Number.isNaN(i.x) && !Number.isNaN(i.y))
  const ignored = parsed.rows.length - valid.length

  const xmax = num(conf.xmax, 10)
  const ymax = num(conf.ymax, 10)
  const grid = quadrantGrid({ width: W, height: H, padding: PAD, xDomain: [0, xmax], yDomain: [0, ymax] })
  const { plot, center, cells } = grid
  const quad = (conf.quadrants ?? '').split(',').map((s) => s.trim())
  const cellList: Array<[keyof typeof cells, string]> = [
    ['topLeft', quad[0] ?? ''],
    ['topRight', quad[1] ?? ''],
    ['bottomLeft', quad[2] ?? ''],
    ['bottomRight', quad[3] ?? ''],
  ]

  const cellEls: ReactNode[] = cellList
    .filter(([, label]) => label.length > 0)
    .map(([key, label]) => {
      const c = cells[key]
      return (
        <Label key={key} x={c.x + c.width / 2} y={c.y + c.height / 2} anchor="middle" variant="muted" size={10}>
          {label}
        </Label>
      )
    })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 340 }} role="img">
        {/* Cadre + croix des axes. */}
        <rect x={plot.x} y={plot.y} width={plot.width} height={plot.height} fill="none" stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
        <line x1={center.x} y1={plot.y} x2={center.x} y2={plot.y + plot.height} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
        <line x1={plot.x} y1={center.y} x2={plot.x + plot.width} y2={center.y} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
        {cellEls}
        {/* Libellés d'axes. */}
        {conf.xlabel && (
          <Label x={plot.x + plot.width / 2} y={plot.y + plot.height + 18} anchor="middle" variant="muted" size={10}>
            {conf.xlabel}
          </Label>
        )}
        {conf.ylabel && (
          <Label x={plot.x} y={plot.y - 12} anchor="start" variant="muted" size={10}>
            {conf.ylabel}
          </Label>
        )}
        {/* Points. */}
        {valid.map((it, i) => {
          const p = grid.place({ x: it.x, y: it.y })
          return (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={3.5} fill={DIAGRAM.accent} />
              <Label x={p.x + 6} y={p.y} anchor="start" variant="node" size={10}>
                {it.label}
              </Label>
            </g>
          )
        })}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
