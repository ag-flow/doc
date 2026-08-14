/** Rendu `df-diagram type="gantt"` — tâches/phases sur une timeline.
 *  Corps : `Tâche | début | fin`. Début/fin en dates `YYYY-MM-DD` (échelle
 *  temporelle) ou en nombres (index). */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { linearScale, niceTicks } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 360
const PAD = 8
const LABEL_W = 100
const ROW_H = 26
const ROW_GAP = 6
const AXIS_H = 22

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function toValue(raw: string, timeMode: boolean): number {
  const s = (raw ?? '').trim()
  if (timeMode) return DATE_RE.test(s) ? Date.parse(s) : NaN
  const n = Number(s.replace(',', '.'))
  return Number.isFinite(n) ? n : NaN
}

function formatTick(v: number, timeMode: boolean): string {
  if (timeMode) return new Date(v).toISOString().slice(0, 10)
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

export function GanttDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 3 })
  const raw = parsed.rows.filter((r) => r[0].length > 0 && r[1].length > 0 && r[2].length > 0)
  // Mode temporel si TOUTES les bornes sont des dates.
  const timeMode = raw.length > 0 && raw.every((r) => DATE_RE.test(r[1].trim()) && DATE_RE.test(r[2].trim()))

  const tasks = raw
    .map((r) => ({ label: r[0], start: toValue(r[1], timeMode), end: toValue(r[2], timeMode) }))
    .filter((tk) => !Number.isNaN(tk.start) && !Number.isNaN(tk.end) && tk.end >= tk.start)
  const ignored = parsed.rows.length - tasks.length
  if (tasks.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const min = Math.min(...tasks.map((tk) => tk.start))
  const max = Math.max(...tasks.map((tk) => tk.end))
  const plotX0 = PAD + LABEL_W
  const plotW = W - plotX0 - PAD
  const x = linearScale([min, max === min ? min + 1 : max], [plotX0, plotX0 + plotW])

  const bodyH = tasks.length * (ROW_H + ROW_GAP) - ROW_GAP
  const axisY = PAD + bodyH + 4
  const H = axisY + AXIS_H

  const ticks = niceTicks(min, max === min ? min + 1 : max, 4)
  const gridEls: ReactNode[] = ticks.map((tk, i) => (
    <g key={`t${i}`}>
      <line x1={x(tk)} y1={PAD} x2={x(tk)} y2={axisY} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
      <Label x={x(tk)} y={axisY + 10} anchor="middle" variant="muted" size={8}>
        {formatTick(tk, timeMode)}
      </Label>
    </g>
  ))

  const barEls: ReactNode[] = tasks.map((tk, i) => {
    const y = PAD + i * (ROW_H + ROW_GAP)
    const bx = x(tk.start)
    const bw = Math.max(2, x(tk.end) - bx)
    return (
      <g key={`b${i}`}>
        <Label x={PAD + 4} y={y + ROW_H / 2} anchor="start" variant="node" size={10}>
          {tk.label}
        </Label>
        <rect x={bx} y={y + 3} width={bw} height={ROW_H - 6} rx={DIAGRAM.radius} fill={DIAGRAM.accent} fillOpacity={0.85} />
      </g>
    )
  })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 420 }} role="img">
        {gridEls}
        {barEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
