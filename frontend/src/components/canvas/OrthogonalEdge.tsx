/**
 * Lien orthogonal à coudes persistés (épic MLD — F6).
 *
 * Le tracé n'est PAS calculé ici : il vient de `route.orthogonalRoute`, la
 * fonction isolée. Ce composant ne fait que la brancher sur le moteur de rendu
 * et rendre les coudes manipulables.
 *
 * Double-clic sur le tracé = poser un coude, double-clic sur un coude = le
 * retirer. Les coudes sont persistés en coordonnées absolues dans le modèle :
 * une fois posés, ils priment sur le tracé automatique.
 */

import { memo, useCallback } from 'react'
import { BaseEdge, EdgeLabelRenderer, useStore, type EdgeProps } from '@xyflow/react'
import type { Anchor } from '../../lib/canvas/anchor'
import type { Point, Side } from '../../lib/canvas/model'
import { orthogonalRoute, toSvgPath } from '../../lib/canvas/route'

export interface OrthogonalEdgeData extends Record<string, unknown> {
  waypoints?: Point[]
  /** Remonte une modification des coudes au document (persistance). */
  onWaypointsChange?: (edgeId: string, waypoints: Point[]) => void
  label?: string
  /** Famille du lien — pour un modèle de données, sa cardinalité. */
  kind?: string
}

/** Cardinalité → notation lue à chaque extrémité.
 *
 *  On écrit la multiplicité DU CÔTÉ où elle se lit : « une commande appartient à
 *  UN client, un client a N commandes ». Sans ces marques, un lien ne dit pas
 *  dans quel sens il se lit — c'est l'information la plus utile d'un MLD. */
const CARDINALITY_ENDS: Record<string, [string, string]> = {
  'one-to-one': ['1', '1'],
  'one-to-many': ['1', 'n'],
  'many-to-one': ['n', '1'],
  'many-to-many': ['n', 'n'],
}

/** Position d'ancrage → côté, tel que le moteur de rendu l'a résolu. */
function sideOf(position: string | undefined): Side {
  switch (position) {
    case 'left':
      return 'left'
    case 'top':
      return 'top'
    case 'bottom':
      return 'bottom'
    default:
      return 'right'
  }
}

function OrthogonalEdgeImpl({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
  style,
}: EdgeProps) {
  const { waypoints, onWaypointsChange, label, kind } = (data ?? {}) as OrthogonalEdgeData
  const ends = kind ? CARDINALITY_ENDS[kind] : undefined
  // Conversion écran → canvas : les coudes sont stockés en coordonnées du
  // document, pas en pixels d'écran, sinon ils bougeraient avec le zoom.
  const transform = useStore((s) => s.transform)

  const source: Anchor = {
    point: { x: sourceX, y: sourceY },
    side: sideOf(sourcePosition),
    degraded: false,
  }
  const target: Anchor = {
    point: { x: targetX, y: targetY },
    side: sideOf(targetPosition),
    degraded: false,
  }

  const points = orthogonalRoute(source, target, waypoints)
  const path = toSvgPath(points)

  const addWaypoint = useCallback(
    (event: React.MouseEvent) => {
      if (!onWaypointsChange) return
      event.stopPropagation()
      const [tx, ty, zoom] = transform
      const at: Point = {
        x: (event.clientX - tx) / zoom,
        y: (event.clientY - ty) / zoom,
      }
      onWaypointsChange(id, [...(waypoints ?? []), at])
    },
    [id, waypoints, onWaypointsChange, transform],
  )

  const removeWaypoint = useCallback(
    (index: number) => {
      if (!onWaypointsChange) return
      onWaypointsChange(id, (waypoints ?? []).filter((_, i) => i !== index))
    },
    [id, waypoints, onWaypointsChange],
  )

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {/* Bande large invisible : viser un trait de 1 px à la souris est pénible. */}
      <path
        d={path}
        data-testid={`edge-hit-${id}`}
        fill="none"
        stroke="transparent"
        strokeWidth={12}
        onDoubleClick={addWaypoint}
        style={{ cursor: onWaypointsChange ? 'crosshair' : undefined }}
      />
      <EdgeLabelRenderer>
        {/* Multiplicités, posées juste après le moignon de chaque extrémité :
            assez près du nœud pour qu'on sache à qui elles se rapportent. */}
        {ends && (
          <>
            <div
              data-testid={`edge-card-source-${id}`}
              className="nodrag nopan absolute rounded bg-[var(--diagram-node-bg,#fff)] px-1 text-[11px] font-medium text-[var(--diagram-text-muted,#52525b)]"
              style={{
                transform: `translate(-50%, -50%) translate(${points[1]?.x ?? sourceX}px, ${
                  (points[1]?.y ?? sourceY) - 10
                }px)`,
              }}
            >
              {ends[0]}
            </div>
            <div
              data-testid={`edge-card-target-${id}`}
              className="nodrag nopan absolute rounded bg-[var(--diagram-node-bg,#fff)] px-1 text-[11px] font-medium text-[var(--diagram-text-muted,#52525b)]"
              style={{
                transform: `translate(-50%, -50%) translate(${
                  points[points.length - 2]?.x ?? targetX
                }px, ${(points[points.length - 2]?.y ?? targetY) - 10}px)`,
              }}
            >
              {ends[1]}
            </div>
          </>
        )}
        {(waypoints ?? []).map((w, i) => (
          <div
            key={`${w.x}:${w.y}:${i}`}
            data-testid={`edge-waypoint-${id}-${i}`}
            onDoubleClick={() => removeWaypoint(i)}
            className="nodrag nopan absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full bg-[var(--diagram-edge,#71717a)]"
            style={{ transform: `translate(${w.x}px, ${w.y}px)` }}
          />
        ))}
        {label && (
          <div
            className="nodrag nopan absolute rounded bg-[var(--diagram-node-bg,#fff)] px-1 text-xs"
            style={{
              transform: `translate(-50%, -50%) translate(${points[Math.floor(points.length / 2)]?.x ?? 0}px, ${
                points[Math.floor(points.length / 2)]?.y ?? 0
              }px)`,
            }}
          >
            {label}
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  )
}

export const OrthogonalEdge = memo(OrthogonalEdgeImpl)
