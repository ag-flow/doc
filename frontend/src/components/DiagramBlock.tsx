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
import { GraphDiagram } from './diagram/renderers/graph'
import { SwimlaneDiagram } from './diagram/renderers/swimlane'
import { QuadrantDiagram } from './diagram/renderers/quadrant'
import { RadarDiagram } from './diagram/renderers/radar'
import { VennDiagram } from './diagram/renderers/venn'
import { MatrixDiagram } from './diagram/renderers/matrix'
import { ScatterDiagram } from './diagram/renderers/scatter'
import { GanttDiagram } from './diagram/renderers/gantt'

/** Types de `df-diagram` (dispatch par attribut `type`). Les Lots 2-5 ajoutent
 *  des entrées ici — le codec et la vue ne changent pas.
 *  Lot 1 : layers, pyramid, nested, tree.
 *  Lot 2 : graph (+ alias sémantiques), swimlane/process, org (= tree). */
const RENDERERS = {
  layers: LayersDiagram,
  pyramid: PyramidDiagram,
  nested: NestedDiagram,
  tree: TreeDiagram,
  // Lot 2 — moteur graphe et ses presets sémantiques.
  graph: GraphDiagram,
  architecture: GraphDiagram,
  dataflow: GraphDiagram,
  'dp-integration': GraphDiagram,
  'high-level': GraphDiagram,
  'it-current-state': GraphDiagram,
  medallion: GraphDiagram,
  // Lot 2 — swimlane / process ; org réutilise l'arbre du Lot 1.
  swimlane: SwimlaneDiagram,
  process: SwimlaneDiagram,
  org: TreeDiagram,
  // Lot 3 — deux axes / ensemblistes.
  quadrant: QuadrantDiagram,
  consultant: QuadrantDiagram,
  radar: RadarDiagram,
  spider: RadarDiagram,
  venn: VennDiagram,
  matrix: MatrixDiagram,
  'security-matrix': MatrixDiagram,
  'dp-security-matrix': MatrixDiagram,
  // Lot 4 — séries quantitatives (scatter/gantt ; bar/line restent en df-chart).
  scatter: ScatterDiagram,
  gantt: GanttDiagram,
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
