/** Codec `df-timeline` : fence ```df-timeline ⇆ bloc custom `dfTimeline`. */
import { ListOrdered } from 'lucide-react'
import { TimelineBlock } from '../../components/TimelineBlock'
import type { SlashContext, SlashItem } from './index'

export interface TimelineProps extends Record<string, unknown> {
  /** Info string brute après le type (attributs, avec l'espace de tête). */
  attrs: string
  /** Corps records brut, sans fence. */
  body: string
}

const SKELETON_BODY = 'Première étape | Décrire ce qui se passe ici.\nDeuxième étape | Puis ce qui suit.'

export const timelineCodec = {
  type: 'dfTimeline',
  pattern: /```df-timeline([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): TimelineProps => ({
    attrs: match[1] ?? '',
    body: match[2].replace(/\n$/, ''),
  }),
  toMarkdown: (props: TimelineProps): string =>
    '```df-timeline' + (props.attrs ?? '') + '\n' + (props.body ?? '') + '\n```',
  spec: () => TimelineBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('timeline.slashTitle'),
    subtext: ctx.t('timeline.slashHint'),
    onItemClick: () => {
      // Squelette VALIDE et pré-rempli : la grammaire se découvre par l'exemple.
      ctx.editor.insertBlocks(
        [{ type: 'dfTimeline', props: { attrs: ` title="${ctx.t('timeline.skeletonTitle')}"`, body: SKELETON_BODY } }],
        ctx.editor.getTextCursorPosition().block,
        'after',
      )
    },
    aliases: ['timeline', 'chronologie', 'étapes', 'plan'],
    group: 'Insérer',
    icon: <ListOrdered size={18} />,
    key: 'df-timeline',
  }),
}
