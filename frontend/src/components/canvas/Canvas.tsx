/**
 * Canvas de diagramme générique (épic MLD — F6).
 *
 * **Frontière d'abstraction** : React Flow est confiné à ce fichier et à ses
 * deux composants frères. L'API publique ne parle que de `CanvasDoc` — un
 * appelant (l'adaptateur MLD de F7) n'importe jamais React Flow.
 *
 * Le composant est CONTRÔLÉ : il reçoit un document et remonte le document
 * modifié. Il ne décide ni de la persistance ni du moment de sauvegarde ; c'est
 * la coquille de page qui s'en charge, comme pour toute autre surface (F4).
 */

import { useCallback, useMemo } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useOnViewportChange,
  type Edge,
  type Node,
  type NodeChange,
  type Viewport as RfViewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { CanvasDoc, CanvasEdge, CanvasNode, Point } from '../../lib/canvas/model'
import { nodeSize } from '../../lib/canvas/model'
import { detailFor, portsVisibleAt, type DetailLevel } from '../../lib/canvas/detail'
import { CanvasNodeView, type CanvasNodeData } from './CanvasNodeView'
import { OrthogonalEdge, type OrthogonalEdgeData } from './OrthogonalEdge'

const NODE_TYPES = { canvasNode: CanvasNodeView }
const EDGE_TYPES = { orthogonal: OrthogonalEdge }

export interface CanvasProps {
  doc: CanvasDoc
  /** Document modifié (déplacement d'un nœud, coude posé, viewport). */
  onChange?: (doc: CanvasDoc) => void
  /** Étiquette d'un nœud — c'est l'adaptateur qui sait la produire. */
  labelOf?: (node: CanvasNode) => string
  /** Clic sur un nœud : ouvrir ce qu'il représente.
   *
   *  Le canvas ne sait pas ce qu'« ouvrir » veut dire — il rend l'identifiant du
   *  nœud, l'appelant navigue. À ne brancher que là où le clic n'a pas déjà un
   *  sens : en édition, il sert à sélectionner et à déplacer. */
  onNodeActivate?: (nodeId: string) => void
  readOnly?: boolean
  className?: string
}

/** Modèle → moteur de rendu. Confiné ici : rien ne fuit vers l'appelant. */
function toRenderNodes(
  doc: CanvasDoc,
  detail: DetailLevel,
  labelOf: (n: CanvasNode) => string,
  activatable: boolean,
): Node[] {
  return doc.nodes.map((n) => ({
    id: n.id,
    type: 'canvasNode',
    position: n.position,
    data: { node: n, detail, label: labelOf(n), activatable } satisfies CanvasNodeData,
    ...nodeSize(n),
  }))
}

function toRenderEdges(
  doc: CanvasDoc,
  portsVisible: boolean,
  onWaypointsChange?: (id: string, w: Point[]) => void,
): Edge[] {
  return doc.edges.map((e) => ({
    id: e.id,
    type: 'orthogonal',
    source: e.source.node,
    target: e.target.node,
    // Ancrage dégradé : sans port utilisable, on retombe sur la poignée de
    // boîte — le lien ne disparaît jamais (cf. `anchor.ts`).
    sourceHandle: portsVisible && e.source.port ? e.source.port : '__box',
    targetHandle: portsVisible && e.target.port ? e.target.port : '__box',
    data: {
      waypoints: e.waypoints,
      onWaypointsChange,
      label: e.label,
      kind: e.kind,
    } satisfies OrthogonalEdgeData,
  }))
}

function CanvasInner({ doc, onChange, labelOf, onNodeActivate, readOnly, className }: CanvasProps) {
  const zoom = doc.viewport?.zoom ?? 1
  const detail = detailFor(zoom)
  const portsVisible = portsVisibleAt(zoom)
  const label = labelOf ?? ((n: CanvasNode) => (n.data?.label as string) ?? n.id)

  const setWaypoints = useCallback(
    (edgeId: string, waypoints: Point[]) => {
      if (!onChange || readOnly) return
      onChange({
        ...doc,
        edges: doc.edges.map((e) =>
          e.id === edgeId
            ? ({ ...e, waypoints: waypoints.length ? waypoints : undefined } as CanvasEdge)
            : e,
        ),
      })
    },
    [doc, onChange, readOnly],
  )

  const nodes = useMemo(
    () => toRenderNodes(doc, detail, label, Boolean(onNodeActivate)),
    [doc, detail, label, onNodeActivate],
  )
  const edges = useMemo(
    () => toRenderEdges(doc, portsVisible, readOnly ? undefined : setWaypoints),
    [doc, portsVisible, readOnly, setWaypoints],
  )

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (!onChange || readOnly) return
      const moved = applyNodeChanges(changes, nodes)
      const byId = new Map(moved.map((n) => [n.id, n.position]))
      onChange({
        ...doc,
        nodes: doc.nodes.map((n) => ({ ...n, position: byId.get(n.id) ?? n.position })),
      })
    },
    [doc, nodes, onChange, readOnly],
  )

  // Le viewport fait partie du document : rouvrir un diagramme doit le retrouver
  // là où on l'avait laissé.
  useOnViewportChange({
    onEnd: (v: RfViewport) => {
      if (!onChange || readOnly) return
      onChange({ ...doc, viewport: { x: v.x, y: v.y, zoom: v.zoom } })
    },
  })

  return (
    <div className={className ?? 'h-[70vh] w-full'} data-testid="canvas" data-detail={detail}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeActivate ? (_, n) => onNodeActivate(n.id) : undefined}
        defaultViewport={doc.viewport ?? { x: 0, y: 0, zoom: 1 }}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={2}
      >
        <Background />
        <Controls showInteractive={!readOnly} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  )
}

export function Canvas(props: CanvasProps) {
  // Le provider est requis par les hooks de viewport ; on l'encapsule pour que
  // l'appelant n'ait pas à connaître le moteur de rendu.
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  )
}
