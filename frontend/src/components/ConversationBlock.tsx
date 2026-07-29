import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { parseAttrs } from '../lib/blockCodecs/records'
import { parseConversation } from '../lib/blockCodecs/conversationParse'
import { BlockFrame, type BlockFrameEdit } from './BlockFrame'
import { DiagnosticBadge } from './TimelineBlock'

const attrsSchema = z.object({
  title: z.string().optional(),
  /** Interlocuteur « local » : ses messages s'alignent à droite. */
  me: z.string().optional(),
  /** Force le format du corps (records | transcript | vtt) ; défaut : détection. */
  format: z.enum(['records', 'transcript', 'vtt']).optional(),
})

/** Vue conversation (exportée pour les tests) : bulles gauche/droite par interlocuteur. */
export function ConversationView({ attrs, body, source, edit }: {
  attrs: string
  body: string
  source: string
  edit?: BlockFrameEdit
}) {
  const { t } = useTranslation()
  const { attrs: rawAttrs, unknown } = parseAttrs(attrs)
  const parsed = attrsSchema.safeParse(rawAttrs)
  const conf = parsed.success ? parsed.data : {}
  const me = conf.me?.trim().toLowerCase() ?? null

  const conv = parseConversation(body, conf.format)
  const rendered = conv.messages.map((m, i) => ({
    ...m,
    mine: me !== null && m.speaker.trim().toLowerCase() === me,
    lead: i === 0 || conv.messages[i - 1].speaker !== m.speaker,
  }))

  const badges: string[] = []
  if (conv.ignored > 0) badges.push(t('records.ignoredLines', { count: conv.ignored }))
  if (!parsed.success || unknown.length > 0) badges.push(t('records.unknownAttrs'))

  return (
    <BlockFrame title={conf.title ?? null} typeLabel="conversation" source={source} edit={edit}>
      <div className="flex flex-col gap-1" data-testid="conversation" data-format={conv.format}>
        {rendered.map((m, i) => (
          <div key={i} className={`flex flex-col ${m.mine ? 'items-end' : 'items-start'}`}>
            {m.lead && (
              <p className={`mb-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                m.mine ? 'text-indigo-500' : 'text-gray-400'
              } ${i > 0 ? 'mt-2' : ''}`}>
                {m.speaker}
                {m.time && (
                  <span className="ml-1.5 font-normal normal-case tracking-normal text-gray-400">
                    {m.time}
                  </span>
                )}
              </p>
            )}
            <p
              className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-1.5 text-sm ${
                m.mine
                  ? 'rounded-tr-sm bg-indigo-50 text-indigo-950'
                  : 'rounded-tl-sm bg-gray-100 text-gray-800'
              }`}
              data-testid={`conversation-msg-${i}`}
            >
              {m.text}
            </p>
          </div>
        ))}
      </div>
      {rendered.length === 0 && (
        <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">{body}</pre>
      )}
      {badges.map((b) => (
        <DiagnosticBadge key={b}>{b}</DiagnosticBadge>
      ))}
    </BlockFrame>
  )
}

/** Bloc BlockNote custom `dfConversation` — fence markdown ```df-conversation. */
export const ConversationBlock = createReactBlockSpec(
  {
    type: 'dfConversation',
    propSchema: {
      attrs: { default: '' },
      body: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <ConversationView
        attrs={props.block.props.attrs}
        body={props.block.props.body}
        source={'```df-conversation' + props.block.props.attrs + '\n' + props.block.props.body + '\n```'}
        edit={
          props.editor.isEditable
            ? {
                attrs: props.block.props.attrs,
                body: props.block.props.body,
                onApply: ({ attrs, body }) =>
                  props.editor.updateBlock(props.block, { props: { attrs, body } }),
              }
            : undefined
        }
      />
    ),
  },
)
