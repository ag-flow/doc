/**
 * Rendu d'un nœud générique du canvas (épic MLD — F6).
 *
 * Générique au sens strict : ce composant ne sait pas ce qu'est une table ni un
 * champ. Il affiche une étiquette et une liste de ports, et c'est l'adaptateur
 * (F7) qui décide de ce que ces ports représentent.
 *
 * Le niveau de détail suit le palier de zoom : sous `fields`, les ports ne sont
 * plus dessinés — et les liens dégradent alors vers le bord (cf. `anchor.ts`).
 */

import { Fragment, memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { CanvasNode, Side } from '../../lib/canvas/model'
import type { DetailLevel } from '../../lib/canvas/detail'
import { BOX_PORT, PORT_SIDES, SIDES, handleId } from './handles'

/** Côté du modèle → position du moteur de rendu. */
const POSITION: Record<Side, Position> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
}

export interface CanvasNodeData extends Record<string, unknown> {
  node: CanvasNode
  detail: DetailLevel
  label: string
  /** Le clic ouvre ce que le nœud représente — se signale au curseur. */
  activatable?: boolean
}

function CanvasNodeViewImpl({ data, selected }: NodeProps) {
  const { node, detail, label, activatable } = data as unknown as CanvasNodeData
  const showPorts = detail === 'fields' && !node.collapsed
  const showLabel = detail !== 'silhouette'

  return (
    <div
      data-testid={`canvas-node-${node.id}`}
      data-detail={detail}
      className={[
        'rounded border bg-[var(--diagram-node-bg,#fff)] text-sm shadow-sm',
        activatable ? 'cursor-pointer' : '',
        selected
          ? 'border-[var(--diagram-node-selected,#2563eb)]'
          : 'border-[var(--diagram-node-border,#d4d4d8)]',
      ].join(' ')}
      style={{ width: node.size?.width, minHeight: node.size?.height }}
    >
      {showLabel && (
        <div className="truncate border-b border-[var(--diagram-node-border,#d4d4d8)] px-2 py-1 font-medium">
          {label}
        </div>
      )}

      {showPorts &&
        (node.ports ?? []).map((port) => (
          <div
            key={port.id}
            data-testid={`canvas-port-${node.id}-${port.id}`}
            className="truncate px-2 py-0.5 text-xs text-[var(--diagram-text-muted,#52525b)]"
          >
            {port.label ?? port.id}
            {/* Un port s'accroche des DEUX côtés, en départ comme en arrivée :
                c'est le lien qui choisit le flanc d'après la position relative
                des boîtes. Figer « source à droite, cible à gauche » forçait les
                liens allant vers la gauche à contourner leur propre boîte. */}
            {PORT_SIDES.map((side) => (
              <Fragment key={side}>
                <Handle
                  type="source"
                  id={handleId(port.id, side)}
                  position={POSITION[side]}
                  className="!h-2 !w-2 !border-0 !bg-[var(--diagram-edge,#71717a)]"
                />
                <Handle
                  type="target"
                  id={handleId(port.id, side)}
                  position={POSITION[side]}
                  className="!h-2 !w-2 !border-0 !bg-[var(--diagram-edge,#71717a)]"
                />
              </Fragment>
            ))}
          </div>
        ))}

      {/* Ancrage dégradé : toujours présent, même quand les ports sont masqués,
          pour qu'un lien ait toujours où se raccrocher — sur les quatre côtés,
          deux boîtes l'une au-dessus de l'autre se reliant en haut/bas. */}
      {SIDES.map((side) => (
        <Fragment key={side}>
          <Handle
            type="source"
            id={handleId(BOX_PORT, side)}
            position={POSITION[side]}
            className="!opacity-0"
          />
          <Handle
            type="target"
            id={handleId(BOX_PORT, side)}
            position={POSITION[side]}
            className="!opacity-0"
          />
        </Fragment>
      ))}
    </div>
  )
}

export const CanvasNodeView = memo(CanvasNodeViewImpl)
