/** Rendu `df-diagram type="radar"` (alias `spider`) — comparaison multi-axes.
 *  Corps : `Axe | valeur` (mono-série) ou `Axe | v1 | v2` (multi-séries avec
 *  header="true" pour nommer les séries). */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { linearScale, radialAngle, radialPoint } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 320
const H = 300
const R = 96
const RINGS = 4
const SERIES_COLOR = [DIAGRAM.accent, DIAGRAM.ink, DIAGRAM.muted]

function num(raw: string): number {
  const n = Number((raw ?? '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}

export function RadarDiagram({ body, conf, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { header: conf.header === 'true' })
  const rows = parsed.rows.filter((r) => r[0].length > 0)
  const ignored = parsed.rows.length - rows.length
  // Au moins 3 axes pour un polygone.
  if (rows.length < 3) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const axes = rows.map((r) => r[0])
  const seriesCount = Math.max(...rows.map((r) => r.length - 1), 1)
  const values = rows.map((r) => Array.from({ length: seriesCount }, (_, s) => num(r[s + 1])))
  const max = Math.max(...values.flat(), 1)
  const scale = linearScale([0, max], [0, R])
  const cx = W / 2
  const cy = H / 2
  const angle = (i: number) => radialAngle(i, axes.length)
  const seriesNames = parsed.header?.slice(1) ?? []

  const rings: ReactNode[] = Array.from({ length: RINGS }, (_, k) => {
    const rr = (R * (k + 1)) / RINGS
    const pts = axes.map((_, i) => radialPoint(cx, cy, rr, angle(i)))
    return (
      <polygon
        key={`ring${k}`}
        points={pts.map((p) => `${p.x},${p.y}`).join(' ')}
        fill="none"
        stroke={DIAGRAM.hairlineColor}
        strokeWidth={DIAGRAM.hairlineWidth}
      />
    )
  })

  const spokes: ReactNode[] = axes.map((label, i) => {
    const rim = radialPoint(cx, cy, R, angle(i))
    const lbl = radialPoint(cx, cy, R + 14, angle(i))
    return (
      <g key={`ax${i}`}>
        <line x1={cx} y1={cy} x2={rim.x} y2={rim.y} stroke={DIAGRAM.hairlineColor} strokeWidth={DIAGRAM.hairlineWidth} />
        <Label x={lbl.x} y={lbl.y} anchor="middle" variant="muted" size={9}>
          {label}
        </Label>
      </g>
    )
  })

  const polys: ReactNode[] = Array.from({ length: seriesCount }, (_, s) => {
    const color = SERIES_COLOR[s % SERIES_COLOR.length]
    // Une valeur négative donnerait un rayon négatif — reflété de l'autre côté
    // du centre en SVG, ce qui mentirait visuellement sur la série.
    const pts = axes.map((_, i) => radialPoint(cx, cy, Math.max(0, scale(values[i][s])), angle(i)))
    return (
      <polygon
        key={`s${s}`}
        points={pts.map((p) => `${p.x},${p.y}`).join(' ')}
        fill={color}
        fillOpacity={0.12}
        stroke={color}
        strokeWidth={1.5}
      />
    )
  })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 340 }} role="img">
        {rings}
        {spokes}
        {polys}
      </svg>
      {seriesCount > 1 && seriesNames.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: 'var(--diagram-muted)' }}>
          {seriesNames.map((name, s) => (
            <li key={s} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SERIES_COLOR[s % SERIES_COLOR.length] }} />
              {name}
            </li>
          ))}
        </ul>
      )}
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
