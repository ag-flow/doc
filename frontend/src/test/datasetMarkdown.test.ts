import { describe, it, expect } from 'vitest'
import {
  parseMarkdownWithBlocks,
  serializeMarkdownWithBlocks,
  type BlockMarkdownEditorApi,
} from '../lib/datasetMarkdown'

const UUID = '11111111-2222-3333-4444-555555555555'

/** Éditeur factice : parse = un bloc paragraphe par ligne non vide ; serialize =
 *  le texte brut du paragraphe. Suffit à exercer le (dé)placement des jetons. */
function makeEditor(
  document: BlockMarkdownEditorApi['document'] = [],
): BlockMarkdownEditorApi {
  return {
    document,
    tryParseMarkdownToBlocks: async (md: string) =>
      md
        .split(/\n+/)
        .map((l) => l.trim())
        .filter((l) => l.length > 0)
        .map((text) => ({ type: 'paragraph', content: [{ type: 'text', text }] })),
    blocksToMarkdownLossy: async (blocks?: unknown[]) => {
      const b = (blocks ?? [])[0] as { content?: { text?: string }[] } | undefined
      return b?.content?.map((n) => n.text ?? '').join('') ?? ''
    },
  }
}

describe('parseMarkdownWithBlocks', () => {
  it('turns a dataset:// token into a dataset block with the right id', async () => {
    const blocks = await parseMarkdownWithBlocks(
      makeEditor(),
      `Intro\n\ndataset://${UUID}\n\nOutro`,
    )
    const ds = blocks.find(
      (b): b is { type: string; props: { datasetId: string } } =>
        typeof b === 'object' && b !== null && (b as { type?: string }).type === 'dataset',
    )
    expect(ds).toBeDefined()
    expect(ds!.props.datasetId).toBe(UUID)
    // Le texte alentour est conservé sous forme de paragraphes.
    expect(blocks.length).toBe(3)
  })

  it('leaves markdown without a token untouched', async () => {
    const blocks = await parseMarkdownWithBlocks(makeEditor(), 'Hello world')
    expect(blocks.every((b) => (b as { type?: string }).type !== 'dataset')).toBe(true)
  })
})

describe('serializeMarkdownWithBlocks', () => {
  it('serializes a dataset block back to a dataset:// token', async () => {
    const editor = makeEditor([
      { type: 'paragraph', props: {} } as never,
      { type: 'dataset', props: { datasetId: UUID } },
    ])
    // Le paragraphe factice n'a pas de content → blocksToMarkdownLossy renvoie ''.
    const md = await serializeMarkdownWithBlocks(editor)
    expect(md).toContain(`dataset://${UUID}`)
  })

  it('round-trips a token through parse then serialize', async () => {
    const parsed = await parseMarkdownWithBlocks(makeEditor(), `dataset://${UUID}`)
    const editor = makeEditor(parsed as BlockMarkdownEditorApi['document'])
    const md = await serializeMarkdownWithBlocks(editor)
    expect(md.trim()).toBe(`dataset://${UUID}`)
  })
})
