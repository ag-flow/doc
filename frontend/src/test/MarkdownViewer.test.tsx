import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    referencesApi: { ...actual.referencesApi, locate: vi.fn() },
  }
})

import { MarkdownViewer } from '../components/MarkdownViewer'

describe('MarkdownViewer — navigation sans remontage', () => {
  it('re-parse quand le contenu change (sommaire / Précédent-Suivant, doc en cache)', async () => {
    const { rerender } = render(
      <MemoryRouter>
        <MarkdownViewer content={'Alpha premier document.'} bare />
      </MemoryRouter>,
    )
    await screen.findByText('Alpha premier document.')

    // Même composant monté, nouveau document : l'article DOIT suivre.
    rerender(
      <MemoryRouter>
        <MarkdownViewer content={'Beta second document.'} bare />
      </MemoryRouter>,
    )
    await screen.findByText('Beta second document.')
    await waitFor(() =>
      expect(screen.queryByText('Alpha premier document.')).not.toBeInTheDocument(),
    )
  })
})
