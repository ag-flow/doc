/** Rendu `df-diagram type="sequence"` — messages dans le temps, acteurs en
 *  lanes verticales. Corps : `A -> B | message` par ligne, ordre = chronologie. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseGraph } from '../../../lib/blockCodecs/graphSpec'
import { lanes, type Rect } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Edge } from '../Edge'
import { Label } from '../Label'
import { Node } from '../Node'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 340
const PAD = 8
const HEADER_H = 26
const MSG_TOP = 16
const MSG_GAP = 30
const MIN_BOX_W = 20

export function SequenceDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const { nodes: actors, edges: messages, ignored } = parseGraph(body)
  if (actors.length === 0 || messages.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const area: Rect = { x: PAD, y: PAD, width: W - 2 * PAD, height: 0 }
  const { bands, centers } = lanes({ area, count: actors.length, orientation: 'vertical', gap: 12 })
  const actorX = (id: string) => centers[actors.findIndex((a) => a.id === id)]
  const boxW = Math.max(MIN_BOX_W, Math.min(96, bands[0].width - 4))

  const msgTop = PAD + HEADER_H + MSG_TOP
  const H = msgTop + messages.length * MSG_GAP + PAD
  const lifeBottom = H - PAD

  const lifelines: ReactNode[] = actors.map((a, i) => (
    <g key={`a${i}`}>
      <line
        x1={centers[i]}
        y1={PAD + HEADER_H}
        x2={centers[i]}
        y2={lifeBottom}
        stroke={DIAGRAM.hairlineColor}
        strokeWidth={DIAGRAM.hairlineWidth}
        strokeDasharray="3 3"
      />
      <Node rect={{ x: centers[i] - boxW / 2, y: PAD, width: boxW, height: HEADER_H }} label={a.label} />
    </g>
  ))

  const msgEls: ReactNode[] = messages.map((m, i) => {
    const y = msgTop + i * MSG_GAP
    const xa = actorX(m.from)
    const xb = actorX(m.to)
    if (xa === undefined || xb === undefined) return null
    if (m.from === m.to) {
      // Auto-message : petite boucle à droite de la lifeline.
      const d = `M${xa} ${y} h22 v12 h-22`
      return (
        <g key={`m${i}`} data-diagram="message">
          <path d={d} fill="none" stroke={DIAGRAM.ink} strokeWidth={DIAGRAM.hairlineWidth} />
          <path d={`M${xa} ${y + 12} l4 -3 l-1 5 Z`} fill={DIAGRAM.ink} />
          {m.label && (
            <Label x={xa + 26} y={y + 6} anchor="start" variant="muted" size={9}>
              {m.label}
            </Label>
          )}
        </g>
      )
    }
    return (
      <g key={`m${i}`} data-diagram="message">
        <Edge from={{ x: xa, y }} to={{ x: xb, y }} arrow />
        {m.label && (
          <Label x={(xa + xb) / 2} y={y - 5} anchor="middle" variant="muted" size={9}>
            {m.label}
          </Label>
        )}
      </g>
    )
  })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 460 }} role="img">
        {lifelines}
        {msgEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
