/**
 * (Dé)sérialisation markdown ⇆ bloc BlockNote `dataset` — miroir de
 * `mermaidMarkdown.ts`, branché à côté du bloc mermaid.
 *
 * Le contenu markdown référence un dataset par un jeton `dataset://<uuid>`
 * (sur sa propre ligne). Au parsing on remplace chaque jeton par un placeholder,
 * on délègue le reste (mermaid inclus) à `parseMarkdownWithMermaid`, puis on
 * réinjecte un bloc `dataset` à chaque placeholder. À la sérialisation, une passe
 * unique gère mermaid ET dataset (les autres blocs → markdown BlockNote).
 */
import { parseMarkdownWithMermaid, type MarkdownEditorApi } from './mermaidMarkdown'

/** Jeton de référence d'un dataset dans le markdown : `dataset://<uuid>`. */
export const DATASET_TOKEN_RE =
  /dataset:\/\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g

const PLACEHOLDER = '%%DATASET_PLACEHOLDER%%'

/** Sur-ensemble de `MarkdownEditorApi` : le bloc dataset porte `datasetId`. */
export interface BlockMarkdownEditorApi {
  document: ReadonlyArray<{ type?: string; props?: { source?: string; datasetId?: string } }>
  tryParseMarkdownToBlocks: (markdown: string) => Promise<unknown[]>
  blocksToMarkdownLossy: (blocks?: unknown[]) => Promise<string>
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
 * Parse un markdown en blocs BlockNote, en gérant les jetons `dataset://` (bloc
 * `dataset`) puis en déléguant mermaid + le reste à `parseMarkdownWithMermaid`.
 */
export async function parseMarkdownWithBlocks(
  editor: BlockMarkdownEditorApi,
  markdown: string,
): Promise<unknown[]> {
  const ids: string[] = []
  const sanitized = (markdown ?? '').replace(DATASET_TOKEN_RE, (_match, id: string) => {
    ids.push(id)
    return `\n${PLACEHOLDER}\n`
  })

  const blocks = await parseMarkdownWithMermaid(editor as MarkdownEditorApi, sanitized)

  let idx = 0
  const result: unknown[] = []
  for (const block of blocks) {
    if (extractPlainText(block).trim() === PLACEHOLDER && idx < ids.length) {
      result.push({ type: 'dataset', props: { datasetId: ids[idx] } })
      idx += 1
    } else {
      result.push(block)
    }
  }
  return result
}

/**
 * Sérialise les blocs courants en markdown. Passe unique : les blocs `mermaid`
 * redeviennent des fences ```mermaid, les blocs `dataset` des jetons
 * `dataset://<uuid>`, le reste passe par `blocksToMarkdownLossy`.
 */
export async function serializeMarkdownWithBlocks(
  editor: BlockMarkdownEditorApi,
): Promise<string> {
  const parts: string[] = []
  for (const block of editor.document) {
    if (block.type === 'mermaid') {
      parts.push('```mermaid\n' + (block.props?.source ?? '') + '\n```')
    } else if (block.type === 'dataset') {
      const id = block.props?.datasetId ?? ''
      if (id) parts.push(`dataset://${id}`)
    } else {
      const md = await editor.blocksToMarkdownLossy([block])
      parts.push(md.trimEnd())
    }
  }
  return parts.filter((p) => p.length > 0).join('\n\n') + '\n'
}
