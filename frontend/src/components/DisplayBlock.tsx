import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { type ReactNode } from 'react'
import { z } from 'zod'
import { parseAttrs } from '../lib/blockCodecs/records'
import { parseDisplay, type DisplayNode } from '../lib/blockCodecs/displayParse'
import { CATALOG } from './displayCatalog'
import { BlockFrame, type BlockFrameEdit } from './BlockFrame'
import { DiagnosticBadge } from './TimelineBlock'

const attrsSchema = z.object({ title: z.string().optional() })

function renderNode(node: DisplayNode, unknowns: Set<string>): ReactNode {
  const entry = CATALOG[node.component]
  const children = node.children.map((c) => (
    <span key={c.id} className="contents">{renderNode(c, unknowns)}</span>
  ))
  if (!entry) {
    // Fallback ADR : composant inconnu → texte grisé, les enfants rendent.
    unknowns.add(node.component)
    return (
      <div data-testid={`display-unknown-${node.id}`}>
        <span className="text-[12px] italic text-ink/[0.45]">
          composant inconnu : {node.component}
        </span>
        {children.length > 0 && <div className="mt-1 flex flex-col gap-2.5">{children}</div>}
      </div>
    )
  }
  return entry.render(node.props, children)
}

/** Vue display (exportée pour les tests) : arbre A2UI simplifié → primitives. */
export function DisplayView({ attrs, body, source, edit }: {
  attrs: string
  body: string
  source: string
  edit?: BlockFrameEdit
}) {
  const { t } = useTranslation()
  const { attrs: rawAttrs, unknown } = parseAttrs(attrs)
  const conf = attrsSchema.safeParse(rawAttrs)
  const title = conf.success ? conf.data.title ?? null : null

  const { root, diagnostics } = parseDisplay(body)
  const unknowns = new Set<string>()
  const rendered = root ? renderNode(root, unknowns) : null

  const badges: string[] = []
  if (unknowns.size > 0) badges.push(t('display.unknownComponents', { count: unknowns.size }))
  if (diagnostics.invalid > 0) badges.push(t('display.invalidEntries', { count: diagnostics.invalid }))
  if (diagnostics.duplicates > 0) badges.push(t('display.duplicates', { count: diagnostics.duplicates }))
  if (diagnostics.orphans > 0) badges.push(t('display.orphans', { count: diagnostics.orphans }))
  if (diagnostics.brokenRefs > 0) badges.push(t('display.brokenRefs', { count: diagnostics.brokenRefs }))
  if (diagnostics.cut > 0) badges.push(t('display.cut', { count: diagnostics.cut }))
  if (!conf.success || unknown.length > 0) badges.push(t('records.unknownAttrs'))

  return (
    <BlockFrame title={title} typeLabel="display" source={source} edit={edit}>
      {rendered !== null ? (
        <div data-testid="display-root">{rendered}</div>
      ) : (
        // JSON illisible : dégradation en source lisible, jamais d'échec.
        <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
      )}
      {badges.map((b) => (
        <DiagnosticBadge key={b}>{b}</DiagnosticBadge>
      ))}
    </BlockFrame>
  )
}

/** Bloc BlockNote custom `dfDisplay` — fences ```df-display (canonique) et
 *  ```display (alias toléré, mémorisé dans `fence` pour le round-trip). */
export const DisplayBlock = createReactBlockSpec(
  {
    type: 'dfDisplay',
    propSchema: {
      fence: { default: 'df-display' },
      attrs: { default: '' },
      body: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <DisplayView
        attrs={props.block.props.attrs}
        body={props.block.props.body}
        source={'```' + props.block.props.fence + props.block.props.attrs + '\n' + props.block.props.body + '\n```'}
        edit={
          props.editor.isEditable
            ? {
                attrs: props.block.props.attrs,
                body: props.block.props.body,
                onApply: ({ attrs, body }) =>
                  props.editor.updateBlock(props.block, { props: { attrs, body } }),
              }
            : undefined
        }
      />
    ),
  },
)
