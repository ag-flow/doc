import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../lib/api', () => ({
  artifactsApi: { upload: vi.fn() },
}))

import { artifactsApi } from '../lib/api'
import { artifactCodec } from '../lib/blockCodecs/artifact'
import { slashItemsFromRegistry } from '../lib/blockCodecs'

const ID = '11111111-2222-3333-4444-555555555555'

function fakeEditor() {
  return {
    insertBlocks: vi.fn(),
    getTextCursorPosition: () => ({ block: { id: 'cur' } }),
  }
}

/** Remplace <input type=file> : click() déclenche onchange avec `file`. */
function stubFilePicker(file: File | null) {
  const realCreate = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    if (tag !== 'input') return realCreate(tag)
    const input = realCreate('input') as HTMLInputElement
    Object.defineProperty(input, 'files', { value: file ? [file] : [], writable: true })
    input.click = () => input.onchange?.(new Event('change'))
    return input
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

describe('action slash « fichier » (artefact)', () => {
  it('le registre expose l’item avec ses alias', () => {
    const items = slashItemsFromRegistry({
      editor: { insertBlocks: () => {}, getTextCursorPosition: () => ({ block: {} }) },
      wsSlug: 'w',
      t: (k) => k,
    })
    const art = items.find((i) => i.key === 'artifact-file')
    expect(art).toBeDefined()
    expect(art!.aliases).toContain('fichier')
  })

  it('téléverse le fichier choisi et insère la puce artefact', async () => {
    vi.mocked(artifactsApi.upload).mockResolvedValue({
      id: ID,
      url: `/api/workspaces/w/artifacts/${ID}`,
      deduplicated: false,
      filename: 'contrat.pdf',
      extension: 'pdf',
      media_type: 'application/pdf',
      size_bytes: 10,
      sha256: 'x',
      crc32: 0,
    })
    const file = new File([new Uint8Array([1, 2, 3])], 'contrat.pdf', { type: 'application/pdf' })
    stubFilePicker(file)

    const editor = fakeEditor()
    const item = artifactCodec.slashItem({ editor, wsSlug: 'w', t: (k) => k })
    item.onItemClick()
    await vi.waitFor(() => expect(artifactsApi.upload).toHaveBeenCalledWith('w', file))
    await vi.waitFor(() => expect(editor.insertBlocks).toHaveBeenCalled())
    const [blocks] = editor.insertBlocks.mock.calls[0]
    expect(blocks[0]).toEqual({ type: 'artifactChip', props: { id: ID, label: '' } })
  })

  it('annulation du sélecteur → aucun upload, aucune insertion', async () => {
    stubFilePicker(null)
    const editor = fakeEditor()
    const item = artifactCodec.slashItem({ editor, wsSlug: 'w', t: (k) => k })
    item.onItemClick()
    // Laisse la microtâche se résoudre.
    await Promise.resolve()
    await Promise.resolve()
    expect(artifactsApi.upload).not.toHaveBeenCalled()
    expect(editor.insertBlocks).not.toHaveBeenCalled()
  })

  it('échec d’upload → onError appelé, pas d’insertion', async () => {
    vi.mocked(artifactsApi.upload).mockRejectedValue(new Error('413'))
    const file = new File([new Uint8Array([1])], 'gros.zip', { type: 'application/zip' })
    stubFilePicker(file)
    const editor = fakeEditor()
    const onError = vi.fn()
    const item = artifactCodec.slashItem({ editor, wsSlug: 'w', t: (k) => k, onError })
    item.onItemClick()
    await vi.waitFor(() => expect(onError).toHaveBeenCalled())
    expect(editor.insertBlocks).not.toHaveBeenCalled()
  })
})
