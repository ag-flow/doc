import { useRef } from 'react'
import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { parseAttrs } from '../lib/blockCodecs/records'
import { BlockFrame, type BlockFrameEdit } from './BlockFrame'
import { DiagnosticBadge } from './TimelineBlock'
import { LayersDiagram } from './diagram/renderers/layers'
import { PyramidDiagram } from './diagram/renderers/pyramid'
import { NestedDiagram } from './diagram/renderers/nested'
import { TreeDiagram } from './diagram/renderers/tree'

/** Types de `df-diagram` couverts par le Lot 1 (dispatch par attribut `type`).
 *  Les Lots 2-5 ajoutent des entrées ici — le codec et la vue ne changent pas. */
const RENDERERS = {
  layers: LayersDiagram,
  pyramid: PyramidDiagram,
  nested: NestedDiagram,
  tree: TreeDiagram,
} as const

type DiagramType = keyof typeof RENDERERS

/** Vue `df-diagram` (exportée pour les tests). */
export function DiagramView({ attrs, body, source, edit }: {
  attrs: string
  body: string
  source: string
  edit?: BlockFrameEdit
}) {
  const { t } = useTranslation()
  const svgRef = useRef<SVGSVGElement | null>(null)
  const { attrs: conf, unknown } = parseAttrs(attrs)
  const type = conf.type ?? 'layers'
  const Renderer = RENDERERS[type as DiagramType] as ((typeof RENDERERS)[DiagramType]) | undefined

  const badges: string[] = []
  if (!Renderer) badges.push(t('diagram.unknownType', { type }))
  if (unknown.length > 0) badges.push(t('records.unknownAttrs'))

  return (
    <BlockFrame
      title={conf.title ?? null}
      typeLabel="diagram"
      source={source}
      svg={() => svgRef.current?.outerHTML ?? null}
      edit={edit}
    >
      {Renderer ? (
        <Renderer body={body} conf={conf} svgRef={svgRef} />
      ) : (
        <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
      )}
      {badges.map((b) => (
        <DiagnosticBadge key={b}>{b}</DiagnosticBadge>
      ))}
    </BlockFrame>
  )
}

/** Bloc BlockNote custom `dfDiagram` — fence markdown ```df-diagram. */
export const DiagramBlock = createReactBlockSpec(
  {
    type: 'dfDiagram',
    propSchema: {
      attrs: { default: '' },
      body: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <DiagramView
        attrs={props.block.props.attrs}
        body={props.block.props.body}
        source={'```df-diagram' + props.block.props.attrs + '\n' + props.block.props.body + '\n```'}
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
