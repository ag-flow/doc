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
  const { waypoints, onWaypointsChange, label } = (data ?? {}) as OrthogonalEdgeData
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
