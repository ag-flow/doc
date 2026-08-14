/** Codec unifié `df-diagram` : fence ```df-diagram ⇆ bloc custom `dfDiagram`.
 *  Discrimine le type de diagramme via l'attribut `type="…"` (modèle df-chart).
 *  Lot 1 : layers, pyramid, nested, tree. Les Lots 2-5 ajoutent des types dans
 *  le dispatcher (components/DiagramBlock.tsx) sans nouveau codec. */
import { Boxes, Building2, Circle, GanttChart, Grid2x2, Grid3x3, Hexagon, Layers, Network, Rows3, ScatterChart, Share2, Triangle } from 'lucide-react'
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
  graph: {
    attrs: ' type="graph"',
    body: 'Web | Frontend\nAPI | Backend\nDB | Base\nWeb -> API\nAPI -> DB | requêtes',
  },
  swimlane: {
    attrs: ' type="swimlane"',
    body: 'Client | Commande\nVente | Devis\nVente | Validation\nLivraison | Expédition',
  },
  org: { attrs: ' type="org"', body: 'Direction\n  Pôle Produit\n    Équipe A\n  Pôle Tech' },
  quadrant: {
    attrs: ' type="quadrant" xlabel="Effort" ylabel="Impact" quadrants="Quick wins,Gros projets,À éviter,Bouche-trous"',
    body: 'Refonte | 8 | 9\nDoc | 2 | 4\nCache | 3 | 7',
  },
  radar: {
    attrs: ' type="radar"',
    body: 'Perf | 8\nCoût | 5\nSécurité | 9\nUX | 6\nMaturité | 7',
  },
  venn: { attrs: ' type="venn"', body: 'A | Frontend\nB | Backend\nA&B | Fullstack' },
  matrix: {
    attrs: ' type="matrix"',
    body: ' | Lire | Écrire | Supprimer\nAdmin | ✓ | ✓ | ✓\nÉditeur | ✓ | ✓ | ✗\nLecteur | ✓ | ✗ | ✗',
  },
  scatter: {
    attrs: ' type="scatter" xlabel="Coût" ylabel="Valeur"',
    body: 'A | 2 | 8\nB | 5 | 5\nC | 8 | 9\nD | 4 | 3',
  },
  gantt: {
    attrs: ' type="gantt"',
    body: 'Cadrage | 2026-01-01 | 2026-01-10\nDév | 2026-01-08 | 2026-02-05\nRecette | 2026-02-05 | 2026-02-15',
  },
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
    {
      title: ctx.t('diagram.graphSlashTitle'),
      subtext: ctx.t('diagram.graphSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'graph'),
      aliases: ['graph', 'graphe', 'architecture', 'flux', 'dataflow', 'medallion'],
      group: 'Insérer',
      icon: <Share2 size={18} />,
      key: 'df-diagram-graph',
    },
    {
      title: ctx.t('diagram.swimlaneSlashTitle'),
      subtext: ctx.t('diagram.swimlaneSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'swimlane'),
      aliases: ['swimlane', 'process', 'processus', 'couloirs', 'lanes'],
      group: 'Insérer',
      icon: <Rows3 size={18} />,
      key: 'df-diagram-swimlane',
    },
    {
      title: ctx.t('diagram.orgSlashTitle'),
      subtext: ctx.t('diagram.orgSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'org'),
      aliases: ['org', 'organigramme', 'ownership', 'équipe'],
      group: 'Insérer',
      icon: <Building2 size={18} />,
      key: 'df-diagram-org',
    },
    {
      title: ctx.t('diagram.quadrantSlashTitle'),
      subtext: ctx.t('diagram.quadrantSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'quadrant'),
      aliases: ['quadrant', 'matrice 2x2', 'consultant', 'bcg'],
      group: 'Insérer',
      icon: <Grid2x2 size={18} />,
      key: 'df-diagram-quadrant',
    },
    {
      title: ctx.t('diagram.radarSlashTitle'),
      subtext: ctx.t('diagram.radarSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'radar'),
      aliases: ['radar', 'spider', 'toile', 'multi-axes'],
      group: 'Insérer',
      icon: <Hexagon size={18} />,
      key: 'df-diagram-radar',
    },
    {
      title: ctx.t('diagram.vennSlashTitle'),
      subtext: ctx.t('diagram.vennSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'venn'),
      aliases: ['venn', 'ensembles', 'recouvrement', 'intersection'],
      group: 'Insérer',
      icon: <Circle size={18} />,
      key: 'df-diagram-venn',
    },
    {
      title: ctx.t('diagram.matrixSlashTitle'),
      subtext: ctx.t('diagram.matrixSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'matrix'),
      aliases: ['matrix', 'matrice', 'permissions', 'security matrix'],
      group: 'Insérer',
      icon: <Grid3x3 size={18} />,
      key: 'df-diagram-matrix',
    },
    {
      title: ctx.t('diagram.scatterSlashTitle'),
      subtext: ctx.t('diagram.scatterSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'scatter'),
      aliases: ['scatter', 'nuage', 'points', 'corrélation'],
      group: 'Insérer',
      icon: <ScatterChart size={18} />,
      key: 'df-diagram-scatter',
    },
    {
      title: ctx.t('diagram.ganttSlashTitle'),
      subtext: ctx.t('diagram.ganttSlashHint'),
      onItemClick: () => insertSkeleton(ctx, 'gantt'),
      aliases: ['gantt', 'planning', 'phases', 'timeline projet'],
      group: 'Insérer',
      icon: <GanttChart size={18} />,
      key: 'df-diagram-gantt',
    },
  ],
}
