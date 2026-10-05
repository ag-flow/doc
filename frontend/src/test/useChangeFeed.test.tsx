import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    changesApi: { ...actual.changesApi, get: vi.fn() },
  }
})

import { changesApi, type ChangeFeedOut } from '../lib/api'
import { useChangeFeed } from '../hooks/useChangeFeed'

const ws = 'ws'

function makeClient() {
  // refetchInterval déclencherait un second appel automatique : on le neutralise
  // pour ne piloter le polling qu'à la main via refetchQueries.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('useChangeFeed', () => {
  beforeEach(() => vi.clearAllMocks())

  it('un événement document invalide les préfixes des listes paginées et du sommaire', async () => {
    const baseline: ChangeFeedOut = { changes: [], next_cursor: 1, has_more: false }
    const withDocumentChange: ChangeFeedOut = {
      changes: [
        {
          seq: 2,
          nature: 'update',
          entity_kind: 'document',
          entity_id: 'd1',
          document_id: 'd1',
          occurred_at: '',
        },
      ],
      next_cursor: 2,
      has_more: false,
    }
    vi.mocked(changesApi.get).mockResolvedValueOnce(baseline)

    const qc = makeClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )

    renderHook(() => useChangeFeed(ws), { wrapper })

    // Baseline : premier fetch établit le curseur, aucune invalidation. On
    // attend que la donnée soit commitée dans le cache ET que l'effet React
    // qui la consomme ait tourné (sinon la 2e requête ci-dessous course avec
    // le traitement de la baseline et fausse le test).
    await waitFor(() => expect(qc.getQueryData(['change-feed', ws])).toEqual(baseline))
    await act(async () => {})
    expect(invalidateSpy).not.toHaveBeenCalled()

    // Un changement `document` arrive au polling suivant.
    vi.mocked(changesApi.get).mockResolvedValueOnce(withDocumentChange)
    await act(async () => {
      await qc.refetchQueries({ queryKey: ['change-feed', ws] })
    })

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled())
    const invalidatedPrefixes = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey[0],
    )

    for (const prefix of [
      'block-documents',
      'block-tree',
      'block-query',
      'block-reading-order',
      'block-type-slugs',
    ]) {
      expect(invalidatedPrefixes).toContain(prefix)
    }
  })
})
