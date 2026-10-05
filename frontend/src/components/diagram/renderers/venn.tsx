/** Rendu `df-diagram type="venn"` — recouvrement de 2 ou 3 ensembles.
 *  Corps : `id | Label` déclare un ensemble ; `A&B | Label` place un libellé
 *  dans une intersection. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Point } from '../../../lib/diagramLayout'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const W = 320
const H = 300
const COLORS = [DIAGRAM.accent, DIAGRAM.ink, DIAGRAM.muted]

interface VennSet {
  id: string
  label: string
}

/** Découpe `id | Label` (label absent → label = id). */
function splitLine(line: string): { id: string; label: string } {
  const bar = line.indexOf('|')
  const id = (bar === -1 ? line : line.slice(0, bar)).trim()
  return { id, label: bar === -1 ? id : line.slice(bar + 1).trim() }
}

/** Sépare corps → ensembles ordonnés + libellés d'intersection (clé triée).
 *  Deux passes : les ensembles d'abord, pour qu'une intersection déclarée avant
 *  ses membres résolve quand même (référence en avant). */
function parseVenn(body: string): { sets: VennSet[]; inters: Map<string, string>; ignored: number } {
  const lines = body
    .split('\n')
    .map((raw) => raw.trim())
    .filter((line) => line.length > 0)
    .map(splitLine)

  const sets: VennSet[] = []
  const index = new Map<string, number>()
  for (const { id, label } of lines) {
    if (id.includes('&') || index.has(id)) continue
    index.set(id, sets.length)
    sets.push({ id, label })
  }

  const inters = new Map<string, string>()
  let ignored = 0
  for (const { id, label } of lines) {
    if (!id.includes('&')) continue
    const members = id.split('&').map((s) => s.trim()).filter((s) => s.length > 0)
    const refs = members.map((m) => index.get(m)).filter((n) => n !== undefined)
    // Un membre jamais déclaré (faute de frappe) → intersection réellement ignorée.
    if (members.length < 2 || refs.length !== members.length) {
      ignored++
      continue
    }
    inters.set(refs.sort((a, b) => a - b).join('-'), label)
  }
  return { sets, inters, ignored }
}

/** Centres + rayon des cercles selon le nombre d'ensembles (2 ou 3). */
function geometry(n: number): { centers: Point[]; r: number } {
  const cx = W / 2
  const cy = H / 2
  if (n === 2) return { centers: [{ x: cx - 30, y: cy }, { x: cx + 30, y: cy }], r: 66 }
  return {
    centers: [{ x: cx, y: cy - 30 }, { x: cx - 34, y: cy + 24 }, { x: cx + 34, y: cy + 24 }],
    r: 58,
  }
}

export function VennDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const { sets, inters, ignored } = parseVenn(body)
  if (sets.length < 2 || sets.length > 3) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const { centers, r } = geometry(sets.length)
  const cx = W / 2
  const cy = H / 2

  const circles: ReactNode[] = centers.map((c, i) => (
    <circle key={`c${i}`} cx={c.x} cy={c.y} r={r} fill={COLORS[i]} fillOpacity={0.12} stroke={COLORS[i]} strokeWidth={1.5} />
  ))

  // Libellés d'ensemble : à l'extérieur de chaque cercle.
  const setLabels: ReactNode[] = centers.map((c, i) => {
    // 2 ensembles : libellé au-dessus du cercle ; 3 : poussé vers l'extérieur.
    const dx = c.x - cx
    const dy = c.y - cy
    const len = Math.hypot(dx, dy) || 1
    const outerX = sets.length === 2 ? c.x : c.x + (dx / len) * (r * 0.7)
    const outerY = sets.length === 2 ? c.y - r - 8 : c.y + (dy / len) * (r * 0.7)
    return (
      <Label key={`sl${i}`} x={outerX} y={outerY} anchor="middle" variant="node" size={11}>
        {sets[i].label}
      </Label>
    )
  })

  // Position d'une intersection : barycentre des centres membres.
  const interAnchor = (key: string): Point => {
    const members = key.split('-').map((s) => Number(s))
    const xs = members.map((m) => centers[m].x)
    const ys = members.map((m) => centers[m].y)
    return { x: xs.reduce((a, b) => a + b, 0) / xs.length, y: ys.reduce((a, b) => a + b, 0) / ys.length }
  }

  const interLabels: ReactNode[] = Array.from(inters.entries())
    .map(([k, label], i) => {
      const p = interAnchor(k)
      return (
        <Label key={`il${i}`} x={p.x} y={p.y} anchor="middle" variant="muted" size={9}>
          {label}
        </Label>
      )
    })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 340 }} role="img">
        {circles}
        {setLabels}
        {interLabels}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
