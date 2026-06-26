const FENCE_RE = /```mermaid\n([\s\S]*?)```/g
const PLACEHOLDER = '%%MERMAID_PLACEHOLDER%%'

/**
 * Sous-ensemble de l'API éditeur BlockNote effectivement utilisé ici.
 *
 * On évite de dépendre du type `BlockNoteEditor<Schema>` paramétré : avec un
 * schéma custom (bloc mermaid), l'inférence générique diverge du type par
 * défaut. Cette interface capture juste les méthodes nécessaires.
 */
export interface MarkdownEditorApi {
  document: ReadonlyArray<{ type?: string; props?: { source?: string } }>
  tryParseMarkdownToBlocks: (markdown: string) => Promise<unknown[]>
  blocksToMarkdownLossy: (blocks?: unknown[]) => Promise<string>
}

interface PendingMermaid {
  source: string
}

function extractPlainText(block: unknown): string {
  if (typeof block !== 'object' || block === null) return ''
  const content = (block as { content?: unknown }).content
  if (!Array.isArray(content)) return ''
  return content
    .map((node) =>
      typeof node === 'object' && node !== null && 'text' in node
        ? String((node as { text: unknown }).text)
        : '',
    )
    .join('')
}

/**
 * Parse un markdown contenant des fences ```mermaid en blocs BlockNote,
 * en remplaçant chaque fence par un bloc custom `mermaid`.
 *
 * BlockNote 0.51 n'expose pas de hook de parsing markdown par bloc custom :
 * on extrait donc les fences nous-mêmes, on parse le reste, puis on réinjecte
 * les blocs mermaid aux emplacements marqués.
 */
export async function parseMarkdownWithMermaid(
  editor: MarkdownEditorApi,
  markdown: string,
): Promise<unknown[]> {
  const pending: PendingMermaid[] = []
  const sanitized = markdown.replace(FENCE_RE, (_match, source: string) => {
    pending.push({ source: source.replace(/\n$/, '') })
    return `\n${PLACEHOLDER}\n`
  })

  const blocks = await editor.tryParseMarkdownToBlocks(sanitized)

  let pendingIndex = 0
  const result: unknown[] = []
  for (const block of blocks) {
    if (extractPlainText(block).trim() === PLACEHOLDER && pendingIndex < pending.length) {
      result.push({ type: 'mermaid', props: { source: pending[pendingIndex].source } })
      pendingIndex += 1
    } else {
      result.push(block)
    }
  }
  return result
}

/**
 * Sérialise les blocs courants en markdown, en réinsérant les blocs mermaid
 * comme fences ```mermaid (BlockNote sérialise un bloc custom inconnu en vide).
 */
export async function serializeMarkdownWithMermaid(
  editor: MarkdownEditorApi,
): Promise<string> {
  const parts: string[] = []
  for (const block of editor.document) {
    if (block.type === 'mermaid') {
      const source = block.props?.source ?? ''
      parts.push('```mermaid\n' + source + '\n```')
    } else {
      const md = await editor.blocksToMarkdownLossy([block])
      parts.push(md.trimEnd())
    }
  }
  return parts.filter((p) => p.length > 0).join('\n\n') + '\n'
}
