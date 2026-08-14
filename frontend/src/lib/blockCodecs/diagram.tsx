/** Codec unifié `df-diagram` : fence ```df-diagram ⇆ bloc custom `dfDiagram`.
 *  Discrimine le type de diagramme via l'attribut `type="…"` (modèle df-chart).
 *  Lot 1 : layers, pyramid, nested, tree. Les Lots 2-5 ajoutent des types dans
 *  le dispatcher (components/DiagramBlock.tsx) sans nouveau codec. */
import { Boxes, Layers, Network, Triangle } from 'lucide-react'
import { DiagramBlock } from '../../components/DiagramBlock'
import type { SlashContext, SlashItem } from './index'

export interface DiagramProps extends Record<string, unknown> {
  attrs: string
  body: string
}

const SKELETONS: Record<string, { attrs: string; body: string }> = {
  layers: { attrs: ' type="layers"', body: 'Présentation | UI\nMétier | logique\nDonnées | stockage' },
  pyramid: { attrs: ' type="pyramid"', body: 'Vision\nStratégie\nExécution' },
  nested: { attrs: ' type="nested"', body: 'Système\n  Module A\n    Fonction 1\n  Module B' },
  tree: { attrs: ' type="tree"', body: 'Racine\n  Enfant 1\n    Petit-enfant\n  Enfant 2' },
}

function insertSkeleton(ctx: SlashContext, kind: keyof typeof SKELETONS): void {
  const sk = SKELETONS[kind]
  ctx.editor.insertBlocks(
    [{ type: 'dfDiagram', props: sk }],
    ctx.editor.getTextCursorPosition().block,
    'after',
  )
}

export const diagramCodec = {
  type: 'dfDiagram',
  pattern: /```df-diagram([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): DiagramProps => ({
    attrs: match[1] ?? '',
    body: match[2].replace(/\n$/, ''),
  }),
  toMarkdown: (props: DiagramProps): string =>
    '```df-diagram' + (props.attrs ?? '') + '\n' + (props.body ?? '') + '\n```',
  spec: () => DiagramBlock(),
  slashItems: (ctx: SlashContext): SlashItem[] => [
    {
      title: ctx.t('diagram.layersSlashTitle'),
      subtext: ctx.t('diagram.layersSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'layers'),
      aliases: ['layers', 'couches', 'pile', 'stack'],
      group: 'Insérer',
      icon: <Layers size={18} />,
      key: 'df-diagram-layers',
    },
    {
      title: ctx.t('diagram.pyramidSlashTitle'),
      subtext: ctx.t('diagram.pyramidSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'pyramid'),
      aliases: ['pyramid', 'pyramide', 'funnel', 'entonnoir'],
      group: 'Insérer',
      icon: <Triangle size={18} />,
      key: 'df-diagram-pyramid',
    },
    {
      title: ctx.t('diagram.nestedSlashTitle'),
      subtext: ctx.t('diagram.nestedSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'nested'),
      aliases: ['nested', 'imbriqué', 'containment', 'boîtes'],
      group: 'Insérer',
      icon: <Boxes size={18} />,
      key: 'df-diagram-nested',
    },
    {
      title: ctx.t('diagram.treeSlashTitle'),
      subtext: ctx.t('diagram.treeSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'tree'),
      aliases: ['tree', 'arbre', 'hiérarchie', 'hierarchy'],
      group: 'Insérer',
      icon: <Network size={18} />,
      key: 'df-diagram-tree',
    },
  ],
}
