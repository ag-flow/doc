import { describe, it, expect, vi } from 'vitest'
import { BlockNoteEditor } from '@blocknote/core'
import { docflowSchema, parseMarkdownWithCodecs, serializeMarkdownWithCodecs, type CodecEditorApi } from '../lib/blockCodecs'
import { docflowPasteHandler } from '../components/MarkdownEditor'

// Presse-papier réel d'un tableau Confluence : HTML + un text/plain qui
// « ressemble à du markdown » (tirets, pipes) — le déclencheur du bug.
const CONFLUENCE_HTML = `
<meta charset="utf-8">
<div class="table-wrap">
<table class="confluenceTable"><colgroup><col/><col/></colgroup><tbody>
<tr><th class="confluenceTh"><p>Colonne A</p></th><th class="confluenceTh"><p>Colonne B</p></th></tr>
<tr><td class="confluenceTd"><p>a1</p></td><td class="confluenceTd"><p>b1</p></td></tr>
</tbody></table>
</div>`

describe('collage de tableaux', () => {
  it('le handler docflow garde le HTML (prioritizeMarkdownOverHTML: false)', () => {
    const defaultPasteHandler = vi.fn(() => true)
    expect(docflowPasteHandler({ defaultPasteHandler })).toBe(true)
    expect(defaultPasteHandler).toHaveBeenCalledWith({ prioritizeMarkdownOverHTML: false })
  })

  it('un tableau Confluence (HTML) parse en bloc table avec ligne d’en-tête', async () => {
    const editor = BlockNoteEditor.create({ schema: docflowSchema })
    const blocks = await editor.tryParseHTMLToBlocks(CONFLUENCE_HTML)
    const table = blocks.find((b: { type: string }) => b.type === 'table') as {
      content: { headerRows?: number; rows: { cells: unknown[] }[] }
    }
    expect(table).toBeDefined()
    expect(table.content.headerRows).toBe(1)
    expect(table.content.rows).toHaveLength(2)
    expect(table.content.rows[0].cells).toHaveLength(2)
  })

  it('round-trip : le tableau collé survit à enregistrer puis rouvrir', async () => {
    const editor = BlockNoteEditor.create({ schema: docflowSchema })
    const pasted = await editor.tryParseHTMLToBlocks(CONFLUENCE_HTML)
    editor.replaceBlocks(editor.document, pasted as never)

    const md = await serializeMarkdownWithCodecs(editor as unknown as CodecEditorApi)
    expect(md).toContain('Colonne A')

    const reopened = BlockNoteEditor.create({ schema: docflowSchema })
    const blocks = await parseMarkdownWithCodecs(reopened as unknown as CodecEditorApi, md)
    expect(blocks.some((b) => (b as { type?: string }).type === 'table')).toBe(true)
  })
})
