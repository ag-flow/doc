import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

vi.mock('../lib/api', () => ({
  prefsApi: {
    get: vi.fn().mockResolvedValue({ key: 'reading-prefs', value: null }),
    set: vi.fn().mockResolvedValue({ key: 'reading-prefs', value: null }),
  },
}))

import { prefsApi } from '../lib/api'
import {
  useReadingPrefs,
  READING_SCALE_STEPS,
  DEFAULT_SCALE_STEP,
  DESKTOP_SCALE_STEP,
  MOBILE_SCALE_STEP,
} from '../hooks/useReadingPrefs'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

/** Simule un viewport mobile (ou non) via matchMedia (absent de jsdom). */
function stubViewport(mobile: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: mobile,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.style.removeProperty('--reading-scale')
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  vi.mocked(prefsApi.get).mockResolvedValue({ key: 'reading-prefs', value: null })
  vi.mocked(prefsApi.set).mockResolvedValue({ key: 'reading-prefs', value: null })
})

describe('useReadingPrefs', () => {
  it('part sur les défauts : panneaux ouverts, échelle par défaut', () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    expect(result.current.tocOpen).toBe(true)
    expect(result.current.propsOpen).toBe(true)
    expect(result.current.scaleStep).toBe(DEFAULT_SCALE_STEP)
    expect(result.current.scale).toBe(READING_SCALE_STEPS[DEFAULT_SCALE_STEP])
    expect(result.current.readingMode).toBe(false)
  })

  it('défaut mobile : échelle à 50 % (sans préférence enregistrée)', () => {
    stubViewport(true)
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    expect(result.current.scaleStep).toBe(MOBILE_SCALE_STEP)
    expect(result.current.scale).toBe(0.5)
  })

  it('défaut desktop : échelle à 100 %', () => {
    stubViewport(false)
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    expect(result.current.scaleStep).toBe(DESKTOP_SCALE_STEP)
    expect(result.current.scale).toBe(1)
  })

  it('une préférence enregistrée prime sur le défaut mobile', async () => {
    stubViewport(true)
    vi.mocked(prefsApi.get).mockResolvedValue({
      key: 'reading-prefs',
      value: { tocOpen: true, propsOpen: true, scaleStep: DESKTOP_SCALE_STEP },
    })
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.scaleStep).toBe(DESKTOP_SCALE_STEP))
  })

  it('reset ramène au défaut de l’appareil courant (mobile → 50 %)', async () => {
    stubViewport(true)
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    act(() => result.current.incScale())
    await waitFor(() => expect(result.current.scaleStep).toBe(MOBILE_SCALE_STEP + 1))
    act(() => result.current.resetScale())
    await waitFor(() => expect(result.current.scaleStep).toBe(MOBILE_SCALE_STEP))
  })

  it('reprend la préférence historique du sommaire (clé legacy) comme défaut', () => {
    localStorage.setItem('docflow.doc.toc', '0')
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    expect(result.current.tocOpen).toBe(false)
  })

  it('toggleProps persiste sur le compte et bascule l’état', async () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    act(() => result.current.toggleProps())
    await waitFor(() => expect(result.current.propsOpen).toBe(false))
    expect(prefsApi.set).toHaveBeenCalledWith(
      'reading-prefs',
      expect.objectContaining({ propsOpen: false }),
    )
  })

  it('setReadingMode(true) replie sommaire ET propriétés', async () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    act(() => result.current.setReadingMode(true))
    await waitFor(() => expect(result.current.readingMode).toBe(true))
    expect(result.current.tocOpen).toBe(false)
    expect(result.current.propsOpen).toBe(false)
  })

  it('incScale / decScale bornent l’échelle aux paliers', async () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    // Descend jusqu’au plancher (lecture read-modify-write sur le cache : les
    // appels s’accumulent sans dépendre d’un re-render entre deux).
    act(() => {
      for (let i = 0; i < 10; i++) result.current.decScale()
    })
    await waitFor(() => expect(result.current.scaleStep).toBe(0))
    expect(result.current.canDec).toBe(false)
    // Monte jusqu’au plafond.
    act(() => {
      for (let i = 0; i < 20; i++) result.current.incScale()
    })
    await waitFor(() => expect(result.current.scaleStep).toBe(READING_SCALE_STEPS.length - 1))
    expect(result.current.canInc).toBe(false)
  })

  it('resetScale rétablit le palier par défaut', async () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    act(() => result.current.incScale())
    act(() => result.current.resetScale())
    await waitFor(() => expect(result.current.scaleStep).toBe(DEFAULT_SCALE_STEP))
  })

  it('applique l’échelle sur la variable CSS de racine --reading-scale', async () => {
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    act(() => result.current.incScale())
    const expected = String(READING_SCALE_STEPS[DEFAULT_SCALE_STEP + 1])
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue('--reading-scale')).toBe(expected),
    )
  })

  it('hydrate depuis la valeur compte quand prefsApi renvoie une préférence', async () => {
    vi.mocked(prefsApi.get).mockResolvedValue({
      key: 'reading-prefs',
      value: { tocOpen: false, propsOpen: true, scaleStep: 4 },
    })
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.tocOpen).toBe(false))
    expect(result.current.scaleStep).toBe(4)
  })

  it('tolère une valeur compte corrompue en retombant sur les défauts', async () => {
    vi.mocked(prefsApi.get).mockResolvedValue({
      key: 'reading-prefs',
      value: { scaleStep: 999 } as never,
    })
    const { result } = renderHook(() => useReadingPrefs(), { wrapper: wrapper() })
    await waitFor(() =>
      expect(result.current.scaleStep).toBe(READING_SCALE_STEPS.length - 1),
    )
  })
})
