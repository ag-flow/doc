import { describe, it, expect } from 'vitest'
import { readClipboardFile } from '../components/editorFilePanel'

function clip(items: Array<{ types: string[]; blobs: Record<string, Blob> }>): Clipboard {
  return {
    read: async () =>
      items.map((it) => ({
        types: it.types,
        getType: async (t: string) => it.blobs[t],
      })) as unknown as ClipboardItem[],
  } as unknown as Clipboard
}

describe('readClipboardFile', () => {
  it('extrait la première image du presse-papier en File', async () => {
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })
    const file = await readClipboardFile(clip([{ types: ['image/png'], blobs: { 'image/png': blob } }]))
    expect(file).not.toBeNull()
    expect(file!.type).toBe('image/png')
    expect(file!.name).toBe('collage.png')
  })

  it('sans image → null', async () => {
    const blob = new Blob(['bonjour'], { type: 'text/plain' })
    const file = await readClipboardFile(clip([{ types: ['text/plain'], blobs: { 'text/plain': blob } }]))
    expect(file).toBeNull()
  })

  it('presse-papier indisponible → null', async () => {
    expect(await readClipboardFile(undefined)).toBeNull()
  })
})
