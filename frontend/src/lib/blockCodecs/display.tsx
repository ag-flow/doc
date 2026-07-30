/** Codec `df-display` : composition libre A2UI simplifiée (ADR 5713844b).
 *
 * Fence canonique ```df-display ; alias ```display toléré en LECTURE mais
 * revendiqué seulement si le corps est un tableau JSON — sinon le bloc
 * traverse en code ordinaire (toBlock → null, contrat du registre). La fence
 * d'origine est mémorisée et resservie : round-trip au caractère près.
 */
import { LayoutGrid } from 'lucide-react'
import { DisplayBlock } from '../../components/DisplayBlock'
import { isDisplayBody } from './displayParse'
import type { SlashContext, SlashItem } from './index'

export interface DisplayProps extends Record<string, unknown> {
  /** Fence d'origine : 'df-display' (canonique) ou 'display' (alias A2UI). */
  fence: string
  /** Info string brute après le type (attributs, avec l'espace de tête). */
  attrs: string
  /** Corps JSON brut, sans fence — JAMAIS reformaté. */
  body: string
}

// Squelette VALIDE (exemple de l'ADR) : la grammaire se découvre par l'exemple.
const SKELETON_BODY = `[
  {"id": "root", "component": "Column", "children": ["title", "cards"]},
  {"id": "title", "component": "Text", "text": "Comparatif", "hint": "h2"},
  {"id": "cards", "component": "Row", "children": ["c1", "c2"]},
  {"id": "c1", "component": "Card", "children": ["c1t", "c1b"]},
  {"id": "c1t", "component": "Text", "text": "Option A", "hint": "h3"},
  {"id": "c1b", "component": "Badge", "text": "Recommandé", "variant": "accent"},
  {"id": "c2", "component": "Card", "children": ["c2t"]},
  {"id": "c2t", "component": "Text", "text": "Option B", "hint": "h3"}
]`

export const displayCodec = {
  type: 'dfDisplay',
  pattern: /```(df-display|display)([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): DisplayProps | null => {
    const fence = match[1]
    const body = match[3].replace(/\n$/, '')
    // Alias sans préfixe : ne capturer que du JSON plausible — un bloc de
    // code ordinaire étiqueté « display » reste un bloc de code.
    if (fence === 'display' && !isDisplayBody(body)) return null
    return { fence, attrs: match[2] ?? '', body }
  },
  toMarkdown: (props: DisplayProps): string =>
    '```' + (props.fence || 'df-display') + (props.attrs ?? '') + '\n' + (props.body ?? '') + '\n```',
  spec: () => DisplayBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('display.slashTitle'),
    subtext: ctx.t('display.slashHint'),
    onItemClick: () => {
      ctx.editor.insertBlocks(
        [{ type: 'dfDisplay', props: { fence: 'df-display', attrs: '', body: SKELETON_BODY } }],
        ctx.editor.getTextCursorPosition().block,
        'after',
      )
    },
    aliases: ['display', 'composition', 'interface', 'a2ui', 'cards'],
    group: 'Insérer',
    icon: <LayoutGrid size={18} />,
    key: 'df-display',
  }),
}
