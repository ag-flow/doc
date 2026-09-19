/** Registre de surfaces par type de contenu + surface de repli (épic MLD — F4a/F4b). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createRef } from 'react'
import {
  FALLBACK_SURFACE,
  SURFACES,
  surfaceFor,
  markdownSurface,
  type ContentEditorHandle,
  type ContentViewerHandle,
} from '../lib/contentSurfaces'
import { PlainTextEditor, PlainTextViewer } from '../components/PlainTextSurface'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

describe('registre de surfaces', () => {
  it('sert le markdown par la surface BlockNote', () => {
    expect(surfaceFor('md')).toBe(markdownSurface)
    expect(SURFACES['md']).toBe(markdownSurface)
  })

  it.each(['table-schema', 'model-layout', 'nimportequoi', ''])(
    'retombe sur le repli pour le type inconnu « %s »',
    (unknown) => {
      expect(surfaceFor(unknown)).toBe(FALLBACK_SURFACE)
    },
  )

  it('retombe sur le repli quand le type est absent', () => {
    expect(surfaceFor(null)).toBe(FALLBACK_SURFACE)
    expect(surfaceFor(undefined)).toBe(FALLBACK_SURFACE)
  })

  it('déclare la copie riche pour le markdown, pas pour le repli', () => {
    // La page doit connaître la capacité AVANT le montage (ref encore nulle).
    expect(markdownSurface.supportsRichCopy).toBe(true)
    expect(FALLBACK_SURFACE.supportsRichCopy).toBeFalsy()
  })
})

describe('surface de repli — texte brut', () => {
  it('affiche le contenu tel quel en lecture', () => {
    const brut = 'fields:\n  - name: id\n    type: uuid\n'
    render(<PlainTextViewer content={brut} />)
    expect(screen.getByTestId('plaintext-viewer')).toHaveTextContent('name: id')
  })

  it('montre le contenu et prévient que le type est inconnu en édition', () => {
    render(<PlainTextEditor initialContent="contenu opaque" onDirty={() => {}} />)
    expect(screen.getByTestId('plaintext-editor')).toBeInTheDocument()
    expect(screen.getByText('editor.unknownContentType')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('contenu opaque')
  })

  it('rend le contenu exactement tel qu\'il a été chargé (aucun reformatage)', async () => {
    // Une surface qui ne comprend pas une grammaire ne doit jamais la réécrire :
    // elle la corromprait.
    const ref = createRef<ContentEditorHandle>()
    const brut = 'a:\n  - 1\n\n\n  # commentaire  \n'
    render(<PlainTextEditor ref={ref} initialContent={brut} onDirty={() => {}} />)
    await expect(ref.current!.getContent()).resolves.toBe(brut)
  })

  it('remonte les modifications et restitue le contenu saisi', async () => {
    const onDirty = vi.fn()
    const ref = createRef<ContentEditorHandle>()
    render(<PlainTextEditor ref={ref} initialContent="" onDirty={onDirty} />)

    await userEvent.type(screen.getByRole('textbox'), 'abc')

    expect(onDirty).toHaveBeenCalled()
    await expect(ref.current!.getContent()).resolves.toBe('abc')
  })

  it('n\'expose pas de copie riche', () => {
    const ref = createRef<ContentViewerHandle>()
    render(<PlainTextViewer ref={ref} content="x" />)
    expect(ref.current?.copyRich).toBeUndefined()
  })
})
