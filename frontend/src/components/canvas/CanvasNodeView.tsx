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

import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { CanvasNode } from '../../lib/canvas/model'
import type { DetailLevel } from '../../lib/canvas/detail'

export interface CanvasNodeData extends Record<string, unknown> {
  node: CanvasNode
  detail: DetailLevel
  label: string
}

function CanvasNodeViewImpl({ data, selected }: NodeProps) {
  const { node, detail, label } = data as unknown as CanvasNodeData
  const showPorts = detail === 'fields' && !node.collapsed
  const showLabel = detail !== 'silhouette'

  return (
    <div
      data-testid={`canvas-node-${node.id}`}
      data-detail={detail}
      className={[
        'rounded border bg-[var(--diagram-node-bg,#fff)] text-sm shadow-sm',
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
            {/* Un port s'accroche des deux côtés : une relation peut partir de
                ce champ comme y arriver. */}
            <Handle
              type="source"
              id={port.id}
              position={Position.Right}
              className="!h-2 !w-2 !border-0 !bg-[var(--diagram-edge,#71717a)]"
            />
            <Handle
              type="target"
              id={port.id}
              position={Position.Left}
              className="!h-2 !w-2 !border-0 !bg-[var(--diagram-edge,#71717a)]"
            />
          </div>
        ))}

      {/* Ancrage dégradé : toujours présent, même quand les ports sont masqués,
          pour qu'un lien ait toujours où se raccrocher. */}
      <Handle type="source" id="__box" position={Position.Right} className="!opacity-0" />
      <Handle type="target" id="__box" position={Position.Left} className="!opacity-0" />
    </div>
  )
}

export const CanvasNodeView = memo(CanvasNodeViewImpl)
