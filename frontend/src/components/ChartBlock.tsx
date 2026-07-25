import { useRef } from 'react'
import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { parseAttrs, parseRecords } from '../lib/blockCodecs/records'
import { BlockFrame } from './BlockFrame'
import { DiagnosticBadge } from './TimelineBlock'

const CHART_TYPES = ['pie', 'donut', 'bar', 'line'] as const
type ChartType = (typeof CHART_TYPES)[number]

// Palette docflow (cohérente avec le thème indigo).
const PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#0ea5e9', '#8b5cf6', '#14b8a6', '#f43f5e']

const attrsSchema = z.object({
  title: z.string().optional(),
  type: z.string().optional(),
  format: z.string().optional(),
  header: z.string().optional(),
  // Réservé (spec 40) — accepté mais non implémenté dans ce lot.
  source: z.string().optional(),
})

interface Series {
  name: string
  color: string
}

interface ChartData {
  labels: string[]
  /** values[rowIndex][seriesIndex] */
  values: number[][]
  series: Series[]
  ignored: number
}

function toNumber(raw: string): number {
  // Tolère la virgule décimale française.
  const n = Number(raw.replace(',', '.'))
  return Number.isFinite(n) ? n : NaN
}

function buildData(body: string, hasHeader: boolean): ChartData {
  const records = parseRecords(body, { header: hasHeader })
  const labels: string[] = []
  const values: number[][] = []
  let ignored = 0
  let seriesCount = 0
  for (const row of records.rows) {
    if (row.length < 2 || row[0].length === 0) {
      ignored++
      continue
    }
    const nums = row.slice(1).map(toNumber)
    if (nums.some((n) => Number.isNaN(n))) {
      ignored++
      continue
    }
    labels.push(row[0])
    values.push(nums)
    seriesCount = Math.max(seriesCount, nums.length)
  }
  // Complète les lignes plus courtes (champs manquants tolérés → 0).
  for (const v of values) while (v.length < seriesCount) v.push(0)
  const headerNames = records.header?.slice(1) ?? []
  const series: Series[] = Array.from({ length: seriesCount }, (_, i) => ({
    name: headerNames[i] || `S${i + 1}`,
    color: PALETTE[i % PALETTE.length],
  }))
  return { labels, values, series, ignored }
}

// ── Rendus SVG ────────────────────────────────────────────────────────────────

function Legend({ labels, colors }: { labels: string[]; colors: string[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
      {labels.map((l, i) => (
        <li key={i} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[i % colors.length] }} />
          <span className="truncate">{l}</span>
        </li>
      ))}
    </ul>
  )
}

function PieDonut({ data, donut, format, svgRef }: {
  data: ChartData
  donut: boolean
  format: string
  svgRef: React.RefObject<SVGSVGElement | null>
}) {
  // Première série uniquement (répartition).
  const vals = data.values.map((v) => v[0]).map((v) => Math.max(0, v))
  const sum = vals.reduce((a, b) => a + b, 0) || 1
  const R = 60
  const C = 2 * Math.PI * R
  let acc = 0
  return (
    <div className="flex flex-wrap items-center gap-4">
      <svg ref={svgRef} viewBox="0 0 160 160" className="h-36 w-36 shrink-0" role="img">
        <g transform="rotate(-90 80 80)">
          {vals.map((v, i) => {
            const frac = v / sum
            const seg = (
              <circle
                key={i}
                cx="80" cy="80" r={R}
                fill="none"
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={donut ? 26 : 60}
                strokeDasharray={`${frac * C} ${C}`}
                strokeDashoffset={-acc * C}
              />
            )
            acc += frac
            return seg
          })}
        </g>
        {donut && <circle cx="80" cy="80" r="34" fill="white" />}
      </svg>
      <Legend
        labels={data.labels.map((l, i) => {
          const v = vals[i]
          return format === 'percent'
            ? `${l} — ${((v / sum) * 100).toFixed(1).replace(/\.0$/, '')} %`
            : `${l} — ${v}`
        })}
        colors={PALETTE}
      />
    </div>
  )
}

function Bars({ data, svgRef }: { data: ChartData; svgRef: React.RefObject<SVGSVGElement | null> }) {
  const max = Math.max(...data.values.flat(), 0) || 1
  const rowH = data.series.length * 12 + 8
  const H = data.labels.length * rowH + 4
  return (
    <div className="space-y-2">
      <svg ref={svgRef} viewBox={`0 0 320 ${H}`} className="w-full" style={{ maxHeight: 320 }} role="img">
        {data.labels.map((label, r) => (
          <g key={r} transform={`translate(0 ${r * rowH})`}>
            <text x="0" y="10" className="fill-gray-600" fontSize="9">{label}</text>
            {data.values[r].map((v, s) => (
              <g key={s}>
                <rect
                  x="90" y={2 + s * 12 + 10} height="9" rx="2"
                  width={Math.max(1, (v / max) * 200)}
                  fill={data.series[s].color}
                />
                <text x={94 + Math.max(1, (v / max) * 200)} y={10 + s * 12 + 10} fontSize="8" className="fill-gray-500">
                  {v}
                </text>
              </g>
            ))}
          </g>
        ))}
      </svg>
      {data.series.length > 1 && (
        <Legend labels={data.series.map((s) => s.name)} colors={data.series.map((s) => s.color)} />
      )}
    </div>
  )
}

function Lines({ data, svgRef }: { data: ChartData; svgRef: React.RefObject<SVGSVGElement | null> }) {
  const W = 320
  const H = 140
  const pad = 14
  const max = Math.max(...data.values.flat(), 0) || 1
  const n = data.labels.length
  const x = (i: number) => (n <= 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (n - 1))
  const y = (v: number) => H - pad - (v / max) * (H - 2 * pad)
  return (
    <div className="space-y-2">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H + 14}`} className="w-full" style={{ maxHeight: 260 }} role="img">
        <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#e5e7eb" />
        {data.series.map((s, si) => (
          <g key={si}>
            <polyline
              fill="none" stroke={s.color} strokeWidth="2"
              points={data.values.map((row, i) => `${x(i)},${y(row[si])}`).join(' ')}
            />
            {data.values.map((row, i) => (
              <circle key={i} cx={x(i)} cy={y(row[si])} r="2.5" fill={s.color} />
            ))}
          </g>
        ))}
        {data.labels.map((l, i) => (
          <text key={i} x={x(i)} y={H + 8} fontSize="8" textAnchor="middle" className="fill-gray-500">
            {l.length > 10 ? l.slice(0, 9) + '…' : l}
          </text>
        ))}
      </svg>
      {data.series.length > 1 && (
        <Legend labels={data.series.map((s) => s.name)} colors={data.series.map((s) => s.color)} />
      )}
    </div>
  )
}

/** Repli tabulaire (type inconnu) — les données restent lisibles. */
function TableFallback({ data }: { data: ChartData }) {
  return (
    <table className="text-xs" data-testid="chart-fallback-table">
      <tbody>
        {data.labels.map((l, r) => (
          <tr key={r} className="border-b border-gray-100">
            <td className="py-0.5 pr-4 text-gray-700">{l}</td>
            {data.values[r].map((v, c) => (
              <td key={c} className="py-0.5 pr-3 text-right font-mono text-gray-600">{v}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Vue principale ────────────────────────────────────────────────────────────

/** Vue chart (exportée pour les tests). */
export function ChartView({ attrs, body, source }: { attrs: string; body: string; source: string }) {
  const { t } = useTranslation()
  const svgRef = useRef<SVGSVGElement | null>(null)
  const { attrs: rawAttrs, unknown } = parseAttrs(attrs)
  const parsed = attrsSchema.safeParse(rawAttrs)
  const conf = parsed.success ? parsed.data : {}

  const requestedType = conf.type ?? 'bar'
  const typeOk = (CHART_TYPES as readonly string[]).includes(requestedType)
  const type: ChartType = typeOk ? (requestedType as ChartType) : 'bar'
  const format = conf.format === 'percent' ? 'percent' : 'count'
  const data = buildData(body, conf.header === 'true')

  const badges: string[] = []
  if (data.ignored > 0) badges.push(t('records.ignoredLines', { count: data.ignored }))
  if (!typeOk) badges.push(t('chart.unknownType', { type: requestedType }))
  if (unknown.length > 0) badges.push(t('records.unknownAttrs'))
  if (format === 'percent' && data.values.length > 0) {
    const sum = data.values.map((v) => v[0]).reduce((a, b) => a + b, 0)
    if (Math.abs(sum - 100) > 0.5) badges.push(t('chart.percentSum'))
  }

  const empty = data.labels.length === 0

  return (
    <BlockFrame
      title={conf.title ?? null}
      typeLabel="chart"
      source={source}
      svg={() => svgRef.current?.outerHTML ?? null}
    >
      {empty ? (
        <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
      ) : !typeOk ? (
        <TableFallback data={data} />
      ) : type === 'pie' || type === 'donut' ? (
        <PieDonut data={data} donut={type === 'donut'} format={format} svgRef={svgRef} />
      ) : type === 'bar' ? (
        <Bars data={data} svgRef={svgRef} />
      ) : (
        <Lines data={data} svgRef={svgRef} />
      )}
      {badges.map((b) => (
        <DiagnosticBadge key={b}>{b}</DiagnosticBadge>
      ))}
    </BlockFrame>
  )
}

/** Bloc BlockNote custom `dfChart` — fence markdown ```df-chart. */
export const ChartBlock = createReactBlockSpec(
  {
    type: 'dfChart',
    propSchema: {
      attrs: { default: '' },
      body: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <ChartView
        attrs={props.block.props.attrs}
        body={props.block.props.body}
        source={'```df-chart' + props.block.props.attrs + '\n' + props.block.props.body + '\n```'}
      />
    ),
  },
)
