/** Rendu `df-diagram type="pyramid"` — niveaux empilés, largeur décroissante
 *  (silhouette) ou proportionnelle aux valeurs (entonnoir). Attribut
 *  `variant="pyramid"` (défaut, sommet en haut) ou `"funnel"` (large en haut). */
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 320
const PAD = 8
const LEVEL_H = 34
const GAP = 2
const MIN_W = 40

function toNumber(raw: string): number {
  const n = Number(raw.replace(',', '.'))
  return Number.isFinite(n) ? n : NaN
}

/** Largeurs (top, bottom) de chaque niveau. */
function levelWidths(values: number[], n: number, contentW: number, funnel: boolean): Array<[number, number]> {
  const numeric = values.some((v) => !Number.isNaN(v))
  if (numeric) {
    const max = Math.max(...values.map((v) => (Number.isNaN(v) ? 0 : v)), 1)
    const w = values.map((v) => Math.max(MIN_W, ((Number.isNaN(v) ? 0 : v) / max) * contentW))
    return w.map((top, i) => [top, w[i + 1] ?? top])
  }
  // Silhouette géométrique : bord ∝ position. Pyramide = apex en haut.
  const boundary = (k: number) => (funnel ? ((n - k) / n) * contentW : (k / n) * contentW)
  return Array.from({ length: n }, (_, i) => [Math.max(MIN_W, boundary(i)), Math.max(MIN_W, boundary(i + 1))])
}

export function PyramidDiagram({ body, conf, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 2 })
  const rows = parsed.rows.filter((r) => r[0].length > 0)
  const ignored = parsed.rows.length - rows.length

  if (rows.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const funnel = conf.variant === 'funnel'
  const values = rows.map((r) => toNumber(r[1] ?? ''))
  const contentW = W - 2 * PAD
  const widths = levelWidths(values, rows.length, contentW, funnel)
  const H = rows.length * LEVEL_H + (rows.length - 1) * GAP + 2 * PAD
  const cx = W / 2

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 360 }} role="img">
        {rows.map((row, i) => {
          const top = PAD + i * (LEVEL_H + GAP)
          const bot = top + LEVEL_H
          const [tw, bw] = widths[i]
          const d = `M${cx - tw / 2} ${top} L${cx + tw / 2} ${top} L${cx + bw / 2} ${bot} L${cx - bw / 2} ${bot} Z`
          return (
            <g key={i}>
              <path d={d} fill={DIAGRAM.paper2} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
              <Label x={cx} y={top + LEVEL_H / 2} anchor="middle" variant="node" size={12}>
                {row[0]}
              </Label>
            </g>
          )
        })}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
