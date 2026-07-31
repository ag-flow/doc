import { describe, it, expect } from 'vitest'
import {
  fileFromClipboardData,
  detectKnownExtension,
  finalFilename,
} from '../components/editorFilePanel'

/** Fabrique un DataTransfer-like : `files` prioritaire, sinon `items`. */
function dt(opts: { files?: File[]; items?: Array<{ kind: string; file: File | null }> }): DataTransfer {
  return {
    files: (opts.files ?? []) as unknown as FileList,
    items: (opts.items ?? []).map((it) => ({
      kind: it.kind,
      getAsFile: () => it.file,
    })) as unknown as DataTransferItemList,
  } as unknown as DataTransfer
}

describe('fileFromClipboardData', () => {
  it('récupère un fichier collé depuis l’explorateur (files) avec son vrai nom', () => {
    const f = new File([new Uint8Array([1])], 'rapport.pdf', { type: 'application/pdf' })
    const got = fileFromClipboardData(dt({ files: [f] }))
    expect(got).toBe(f)
    expect(got!.name).toBe('rapport.pdf')
  })

  it('récupère une image collée exposée en items (kind=file)', () => {
    const img = new File([new Uint8Array([2])], 'image.png', { type: 'image/png' })
    const got = fileFromClipboardData(dt({ items: [{ kind: 'file', file: img }] }))
    expect(got).toBe(img)
  })

  it('ignore le texte (kind=string) → null', () => {
    const got = fileFromClipboardData(dt({ items: [{ kind: 'string', file: null }] }))
    expect(got).toBeNull()
  })

  it('presse-papier vide → null', () => {
    expect(fileFromClipboardData(null)).toBeNull()
    expect(fileFromClipboardData(dt({}))).toBeNull()
  })
})

describe('detectKnownExtension', () => {
  const known = ['pdf', 'png', 'jpg']
  it('extension connue en fin de nom → renvoyée en minuscule', () => {
    expect(detectKnownExtension('Rapport.PDF', known)).toBe('pdf')
  })
  it('extension inconnue → chaîne vide', () => {
    expect(detectKnownExtension('archive.tar', known)).toBe('')
  })
  it('sans extension → chaîne vide', () => {
    expect(detectKnownExtension('sans-extension', known)).toBe('')
  })
})

describe('finalFilename', () => {
  it('ajoute l’extension du type choisi si absente', () => {
    expect(finalFilename('rapport', 'pdf')).toBe('rapport.pdf')
  })
  it('n’ajoute rien si déjà présente (insensible à la casse)', () => {
    expect(finalFilename('rapport.PDF', 'pdf')).toBe('rapport.PDF')
  })
  it('sans type sélectionné → nom tel quel', () => {
    expect(finalFilename('image.png', '')).toBe('image.png')
  })
})
