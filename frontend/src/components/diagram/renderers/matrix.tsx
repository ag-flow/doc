/** Rendu `df-diagram type="matrix"` (alias `security-matrix`, `dp-security-matrix`)
 *  — grille lignes × colonnes (ex. permissions par rôle). Corps : 1ʳᵉ ligne =
 *  en-tête des colonnes avec un coin vide (`| Col1 | Col2`), puis
 *  `Ligne | v1 | v2` par ligne. Cellule : ✓/✗ (permission) ou texte libre. */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { parseRecords } from '../../../lib/blockCodecs/records'
import { DiagnosticBadge } from '../../TimelineBlock'
import { Label } from '../Label'
import { DIAGRAM } from '../svgTokens'
import type { RendererProps } from './types'

const PAD = 8
const LABEL_W = 96
const COL_W = 66
const HEAD_H = 28
const ROW_H = 28

const ALLOW = /^(✓|v|yes|oui|y|o|1|true|allow|rw|r|w)$/i
const DENY = /^(✗|no|non|n|0|false|deny|-|—|)$/i

type Cell = { kind: 'allow' } | { kind: 'deny' } | { kind: 'text'; text: string }

function classify(raw: string): Cell {
  const v = (raw ?? '').trim()
  if (ALLOW.test(v)) return { kind: 'allow' }
  if (DENY.test(v)) return { kind: 'deny' }
  return { kind: 'text', text: v }
}

export function MatrixDiagram({ body, svgRef }: RendererProps) {
  const { t } = useTranslation()
  const parsed = parseRecords(body, { header: true })
  const cols = (parsed.header ?? []).slice(1)
  const rows = parsed.rows.filter((r) => r[0].length > 0)
  const ignored = parsed.rows.length - rows.length
  if (cols.length === 0 || rows.length === 0) {
    return <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
  }

  const W = PAD + LABEL_W + cols.length * COL_W + PAD
  const H = PAD + HEAD_H + rows.length * ROW_H + PAD
  const gridX0 = PAD + LABEL_W
  const gridY0 = PAD + HEAD_H

  const headEls: ReactNode[] = cols.map((c, i) => (
    <Label key={`h${i}`} x={gridX0 + i * COL_W + COL_W / 2} y={PAD + HEAD_H / 2} anchor="middle" variant="muted" size={10}>
      {c}
    </Label>
  ))

  const rowEls: ReactNode[] = rows.map((row, r) => {
    const y = gridY0 + r * ROW_H
    const cyc = y + ROW_H / 2
    const cells: ReactNode[] = cols.map((_, c) => {
      const x = gridX0 + c * COL_W
      const cell = classify(row[c + 1] ?? '')
      return (
        <g key={`cell${r}-${c}`}>
          <rect
            x={x}
            y={y}
            width={COL_W}
            height={ROW_H}
            fill={cell.kind === 'allow' ? DIAGRAM.accent : 'none'}
            fillOpacity={cell.kind === 'allow' ? 0.16 : undefined}
            stroke={DIAGRAM.hairlineColor}
            strokeWidth={DIAGRAM.hairlineWidth}
          />
          {cell.kind === 'allow' && (
            <Label x={x + COL_W / 2} y={cyc} anchor="middle" variant="node" size={12}>
              ✓
            </Label>
          )}
          {cell.kind === 'text' && (
            <Label x={x + COL_W / 2} y={cyc} anchor="middle" variant="mono" size={9}>
              {cell.text}
            </Label>
          )}
        </g>
      )
    })
    return (
      <g key={`row${r}`}>
        <Label x={PAD + 4} y={cyc} anchor="start" variant="node" size={10}>
          {row[0]}
        </Label>
        {cells}
      </g>
    )
  })

  return (
    <>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 420 }} role="img">
        {headEls}
        {rowEls}
      </svg>
      {ignored > 0 && <DiagnosticBadge>{t('records.ignoredLines', { count: ignored })}</DiagnosticBadge>}
    </>
  )
}
