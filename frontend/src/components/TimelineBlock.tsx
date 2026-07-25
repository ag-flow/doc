import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { parseAttrs, parseRecords } from '../lib/blockCodecs/records'
import { BlockFrame } from './BlockFrame'

const attrsSchema = z.object({
  title: z.string().optional(),
  label: z.string().optional(),
})

const rowSchema = z.tuple([z.string().min(1), z.string()])

/** Badge de diagnostic commun (lignes ignorées, attributs inconnus…). */
export function DiagnosticBadge({ children }: { children: string }) {
  return (
    <p
      className="mt-2 inline-block rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700"
      data-testid="block-diagnostic"
    >
      {children}
    </p>
  )
}

/** Vue timeline (exportée pour les tests) : rail vertical d'étapes numérotées. */
export function TimelineView({ attrs, body, source }: { attrs: string; body: string; source: string }) {
  const { t } = useTranslation()
  const { attrs: rawAttrs, unknown } = parseAttrs(attrs)
  const parsed = attrsSchema.safeParse(rawAttrs)
  const conf = parsed.success ? parsed.data : {}
  const label = conf.label || t('timeline.defaultLabel')

  const records = parseRecords(body, { fields: 2 })
  const steps: { title: string; description: string }[] = []
  let ignored = 0
  for (const row of records.rows) {
    const r = rowSchema.safeParse(row)
    if (r.success) steps.push({ title: r.data[0], description: r.data[1] })
    else ignored++
  }

  const badges: string[] = []
  if (ignored > 0) badges.push(t('records.ignoredLines', { count: ignored }))
  if (!parsed.success || unknown.length > 0) badges.push(t('records.unknownAttrs'))

  return (
    <BlockFrame title={conf.title ?? null} typeLabel="timeline" source={source}>
      <ol className="relative ml-2 border-l-2 border-indigo-100 pl-5" data-testid="timeline">
        {steps.map((step, i) => (
          <li key={i} className="relative pb-4 last:pb-0">
            <span className="absolute -left-[27px] top-0.5 h-3 w-3 rounded-full border-2 border-white bg-indigo-500 shadow" />
            <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-500">
              {label} {i + 1}
            </p>
            <p className="text-sm font-semibold text-gray-900">{step.title}</p>
            {step.description && <p className="text-sm text-gray-600">{step.description}</p>}
          </li>
        ))}
      </ol>
      {steps.length === 0 && (
        <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
      )}
      {badges.map((b) => (
        <DiagnosticBadge key={b}>{b}</DiagnosticBadge>
      ))}
    </BlockFrame>
  )
}

/** Bloc BlockNote custom `dfTimeline` — fence markdown ```df-timeline. */
export const TimelineBlock = createReactBlockSpec(
  {
    type: 'dfTimeline',
    propSchema: {
      attrs: { default: '' },
      body: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <TimelineView
        attrs={props.block.props.attrs}
        body={props.block.props.body}
        source={'```df-timeline' + props.block.props.attrs + '\n' + props.block.props.body + '\n```'}
      />
    ),
  },
)
