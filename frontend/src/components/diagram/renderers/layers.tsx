/** Rendu `df-diagram type="layers"` — pile de couches pleine largeur, haut→bas. */
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { lanes, type Rect } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Node } from '../Node'
import type { RendererProps } from './types'

const W = 320
const PAD = 8
const ROW_H = 32
const GAP = 6

export function LayersDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { fields: 2 })
  const rows = parsed.rows.filter((r) => r[0].length > 0)
  const ignored = parsed.rows.length - rows.length

  if (rows.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const area: Rect = { x: PAD, y: PAD, width: W - 2 * PAD, height: rows.length * ROW_H + (rows.length - 1) * GAP }
  const { bands } = lanes({ area, count: rows.length, orientation: 'horizontal', gap: GAP })
  const H = area.height + 2 * PAD

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 360 }} role="img">
        {bands.map((b, i) => (
          <Node key={i} rect={b} label={rows[i][0]} sublabel={rows[i][1] || undefined} />
        ))}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
