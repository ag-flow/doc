import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    referencesApi: { ...actual.referencesApi, locate: vi.fn() },
    artifactsApi: { ...actual.artifactsApi, getLink: vi.fn() },
  }
})

import { MarkdownViewer, matchArtifactHref } from '../components/MarkdownViewer'

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

describe('matchArtifactHref — résolveur de lien artefact (fiche 1e2d86c0)', () => {
  const ID = '86311e1e-16d6-4c7c-bab5-afe5a5f8a5c2'

  it('schéma artifact:// → workspace du contexte courant', () => {
    expect(matchArtifactHref(`artifact://${ID}`, 'mon-ws')).toEqual({ ws: 'mon-ws', id: ID })
  })

  it('schéma artifact:// sans workspace courant → null (pas de résolution possible)', () => {
    expect(matchArtifactHref(`artifact://${ID}`, null)).toBeNull()
  })

  it('URL brute /api/.../artifacts/{id} (cas token manquant) → workspace de l’URL', () => {
    expect(
      matchArtifactHref(`/api/workspaces/jobs-professionnal/artifacts/${ID}`, 'autre-ws'),
    ).toEqual({ ws: 'jobs-professionnal', id: ID })
  })

  it('URL brute ABSOLUE (clic navigateur) → interceptée', () => {
    expect(
      matchArtifactHref(`https://doc.yoops.org/api/workspaces/jobs-professionnal/artifacts/${ID}`, null),
    ).toEqual({ ws: 'jobs-professionnal', id: ID })
  })

  it('URL déjà signée (/download) NON interceptée — elle porte sa propre auth', () => {
    expect(
      matchArtifactHref(`/api/workspaces/w/artifacts/${ID}/download?exp=1&sig=ab`, 'w'),
    ).toBeNull()
  })

  it('lien quelconque → null', () => {
    expect(matchArtifactHref('https://exemple.org/page', 'w')).toBeNull()
    expect(matchArtifactHref('docflow://doc/' + ID, 'w')).toBeNull()
  })
})
