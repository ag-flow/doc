/** Codec `df-conversation` : fence ```df-conversation ⇆ bloc custom `dfConversation`. */
import { MessagesSquare } from 'lucide-react'
import { ConversationBlock } from '../../components/ConversationBlock'
import type { SlashContext, SlashItem } from './index'

export interface ConversationProps extends Record<string, unknown> {
  /** Info string brute après le type (attributs, avec l'espace de tête). */
  attrs: string
  /** Corps records brut, sans fence. */
  body: string
}

const SKELETON_BODY =
  'Alice | Première réplique de la conversation.\nBob | Réponse.\nAlice | Suite de l\'échange.'

export const conversationCodec = {
  type: 'dfConversation',
  pattern: /```df-conversation([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): ConversationProps => ({
    attrs: match[1] ?? '',
    body: match[2].replace(/\n$/, ''),
  }),
  toMarkdown: (props: ConversationProps): string =>
    '```df-conversation' + (props.attrs ?? '') + '\n' + (props.body ?? '') + '\n```',
  spec: () => ConversationBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('conversation.slashTitle'),
    subtext: ctx.t('conversation.slashHint'),
    onItemClick: () => {
      // Squelette VALIDE et pré-rempli : la grammaire se découvre par l'exemple.
      ctx.editor.insertBlocks(
        [{
          type: 'dfConversation',
          props: { attrs: ` title="${ctx.t('conversation.skeletonTitle')}" me="Alice"`, body: SKELETON_BODY },
        }],
        ctx.editor.getTextCursorPosition().block,
        'after',
      )
    },
    aliases: ['conversation', 'chat', 'dialogue', 'échange', 'messages'],
    group: 'Insérer',
    icon: <MessagesSquare size={18} />,
    key: 'df-conversation',
  }),
}
