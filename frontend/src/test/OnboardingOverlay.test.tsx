import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import { ToastProvider } from '../components/Toast'
import { OnboardingOverlay } from '../onboarding/OnboardingOverlay'
import { prefsApi } from '../lib/api'

vi.mock('../lib/api', () => ({
  prefsApi: { get: vi.fn(), set: vi.fn() },
}))

function mockPrefs(value: unknown) {
  ;(prefsApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({ key: 'onboarding', value })
  ;(prefsApi.set as ReturnType<typeof vi.fn>).mockResolvedValue({ key: 'onboarding', value })
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <OnboardingOverlay />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('OnboardingOverlay', () => {
  beforeEach(() => vi.clearAllMocks())

  it('affiche la bulle de l’étape courante sur sa page', async () => {
    mockPrefs({ step: 0, disabled: false })
    renderAt('/workspaces')
    const bulle = await screen.findByTestId('onboarding-bulle')
    expect(bulle).toHaveTextContent('Bienvenue dans docflow')
    expect(screen.getByText('Étape 1 sur 6')).toBeInTheDocument()
  })

  it('« Suivant » avance l’index persisté', async () => {
    mockPrefs({ step: 0, disabled: false })
    renderAt('/workspaces')
    await screen.findByTestId('onboarding-bulle')
    fireEvent.click(screen.getByText('Suivant'))
    await waitFor(() =>
      expect(prefsApi.set).toHaveBeenCalledWith('onboarding', { step: 1, disabled: false }),
    )
  })

  it('hors de la page de l’étape : contrôles visibles, pas de bulle (pause silencieuse)', async () => {
    mockPrefs({ step: 0, disabled: false }) // étape 0 = /workspaces, mais on est sur /me
    renderAt('/me')
    expect(await screen.findByText('Rouvrir le guide')).toBeInTheDocument()
    expect(screen.queryByTestId('onboarding-bulle')).not.toBeInTheDocument()
  })

  it('désactivé : ni bulle ni contrôles une fois la préférence résolue', async () => {
    mockPrefs({ step: 0, disabled: true })
    renderAt('/workspaces')
    // La préférence par défaut affiche d'abord la bulle ; une fois `disabled`
    // résolu, tout disparaît (le parcours est arrêté).
    await waitFor(() => {
      expect(screen.queryByTestId('onboarding-bulle')).not.toBeInTheDocument()
      expect(screen.queryByText('Rouvrir le guide')).not.toBeInTheDocument()
    })
  })
})
