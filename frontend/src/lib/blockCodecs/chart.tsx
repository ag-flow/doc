/** Codec `df-chart` : fence ```df-chart ⇆ bloc custom `dfChart`. */
import { PieChart } from 'lucide-react'
import { ChartBlock } from '../../components/ChartBlock'
import type { SlashContext, SlashItem } from './index'

export interface ChartProps extends Record<string, unknown> {
  /** Info string brute après le type (attributs, avec l'espace de tête). */
  attrs: string
  /** Corps records brut, sans fence. */
  body: string
}

const SKELETON_BODY = 'Fait | 12\nEn cours | 5\nÀ faire | 3'

export const chartCodec = {
  type: 'dfChart',
  pattern: /```df-chart([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): ChartProps => ({
    attrs: match[1] ?? '',
    body: match[2].replace(/\n$/, ''),
  }),
  toMarkdown: (props: ChartProps): string =>
    '```df-chart' + (props.attrs ?? '') + '\n' + (props.body ?? '') + '\n```',
  spec: () => ChartBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('chart.slashTitle'),
    subtext: ctx.t('chart.slashHint'),
    onItemClick: () => {
      // Squelette VALIDE et pré-rempli : la grammaire se découvre par l'exemple.
      ctx.editor.insertBlocks(
        [{ type: 'dfChart', props: { attrs: ` type="donut" title="${ctx.t('chart.skeletonTitle')}"`, body: SKELETON_BODY } }],
        ctx.editor.getTextCursorPosition().block,
        'after',
      )
    },
    aliases: ['chart', 'graphique', 'camembert', 'barres', 'courbe', 'pie', 'bar', 'line'],
    group: 'Insérer',
    icon: <PieChart size={18} />,
    key: 'df-chart',
  }),
}
