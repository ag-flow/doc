/** Rendu `df-diagram type="scatter"` — nuage de points (distribution/corrélation).
 *  Corps : `label | x | y` (label optionnel). Consomme cartesianFrame + Grid. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { cartesianFrame, extentOf, type Extent } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Grid } from '../Grid'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 340
const H = 280
const PADDING = { left: 34, right: 14, top: 14, bottom: 28 }

function num(raw: string): number {
  const n = Number((raw ?? '').replace(',', '.'))
  return Number.isFinite(n) ? n : NaN
}

/** Domaine avec petite marge ; borne dégénérée élargie. */
function padDomain(ext: Extent): Extent {
  const [a, b] = ext
  if (a === b) return [a - 1, b + 1]
  const m = (b - a) * 0.05
  return [a - m, b + m]
}

export function ScatterDiagram({ body, conf, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 3 })
  const pts = parsed.rows
    .map((r) => ({ label: r[0], x: num(r[1]), y: num(r[2]) }))
    .filter((p) => !Number.isNaN(p.x) && !Number.isNaN(p.y))
  const ignored = parsed.rows.length - pts.length
  if (pts.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const frame = cartesianFrame({
    width: W,
    height: H,
    padding: PADDING,
    xDomain: padDomain(extentOf(pts.map((p) => p.x))),
    yDomain: padDomain(extentOf(pts.map((p) => p.y))),
  })

  const pointEls: ReactNode[] = pts.map((p, i) => {
    const c = frame.project({ x: p.x, y: p.y })
    return <circle key={i} cx={c.x} cy={c.y} r={3.5} fill={DIAGRAM.accent} fillOpacity={0.85} />
  })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 320 }} role="img">
        <Grid frame={frame} labels />
        {pointEls}
        {conf.xlabel && (
          <Label x={frame.plot.x + frame.plot.width / 2} y={H - 6} anchor="middle" variant="muted" size={10}>
            {conf.xlabel}
          </Label>
        )}
        {conf.ylabel && (
          <Label x={frame.plot.x} y={4} anchor="start" variant="muted" size={10}>
            {conf.ylabel}
          </Label>
        )}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
