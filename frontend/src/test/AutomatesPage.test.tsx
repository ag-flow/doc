import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

/**
 * Test-INVENTAIRE de l'écran Automates : la refonte Broadsheet ne doit perdre
 * AUCUNE des personnalisations accumulées. Chaque commande de ligne est
 * vérifiée par son testid ET par l'appel API qu'elle déclenche.
 */

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    automationsApi: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      listRuns: vi.fn(),
      replay: vi.fn(),
      runNext: vi.fn(),
      advance: vi.fn(),
      cursorBack: vi.fn(),
      clone: vi.fn(),
      clearRuns: vi.fn(),
      reorder: vi.fn(),
      pushEvents: vi.fn(),
    },
    contractsApi: { list: vi.fn(), detail: vi.fn() },
    eventsProducerApi: { catalog: vi.fn() },
    secretsApi: { list: vi.fn() },
    docsApi: { getBlocks: vi.fn() },
    api: { get: vi.fn() },
  }
})

import {
  api, automationsApi, contractsApi, docsApi, eventsProducerApi, secretsApi,
  type AutomationOut,
} from '../lib/api'
import { AutomatesPage } from '../pages/AutomatesPage'
import { ToastProvider } from '../components/Toast'

function makeAuto(over: Partial<AutomationOut>): AutomationOut {
  return {
    id: 'a1', workspace_technical_key: 'wk', label: 'Vers RAG', active: true,
    pending_count: 0, position: 1, workspace_slugs: ['ws1'],
    event_codes: ['docflow.document.updated.v1'], block_slugs: [], functional_type_slugs: [],
    stop_chain: false, on_create: false, on_update: true, delay_minutes: 0,
    contract_ref: null, operation_id: null, url: 'https://rag.example/api',
    http_method: 'POST', body_template: '{"doc": "{title}"}', headers: [],
    created_at: '', updated_at: '',
    last_run_at: '2026-07-27T08:00:00Z', last_run_status: 'ok', last_run_http_status: 200,
    ...over,
  }
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/ws/ws1/automations']}>
          <Routes>
            <Route path="/ws/:wsSlug/automations" element={<AutomatesPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(automationsApi.list).mockResolvedValue([makeAuto({})])
  vi.mocked(automationsApi.listRuns).mockResolvedValue([])
  vi.mocked(contractsApi.list).mockResolvedValue([])
  vi.mocked(eventsProducerApi.catalog).mockResolvedValue({ revision: 'r', specVersion: '1', events: [] })
  vi.mocked(secretsApi.list).mockResolvedValue([])
  vi.mocked(docsApi.getBlocks).mockResolvedValue([])
  vi.mocked(api.get).mockResolvedValue([])
})

describe('AutomatesPage — inventaire des commandes de ligne', () => {
  it('chaque commande est présente : poignée, rang, replier, curseur, test, avance, toggle, clone, éditer, supprimer', async () => {
    renderPage()
    const card = await screen.findByTestId('auto-card-a1')
    // Rang à deux chiffres + poignée de drag
    expect(card).toHaveTextContent('01')
    expect(card.querySelector('[draggable]') ?? card).toHaveAttribute('draggable')
    // Badge d'état du curseur
    expect(screen.getByTestId('pending-a1')).toHaveTextContent('à jour')
    // Commandes du curseur d'events
    expect(screen.getByTestId('cursor-back-a1')).toBeInTheDocument()
    expect(screen.getByTestId('run-next-a1')).toBeInTheDocument()
    expect(screen.getByTestId('advance-a1')).toBeInTheDocument()
    // Toggle avec sémantique switch
    expect(screen.getByTestId('toggle-active-a1')).toHaveAttribute('role', 'switch')
    expect(screen.getByTestId('toggle-active-a1')).toHaveAttribute('aria-checked', 'true')
    // Clone / éditer / supprimer
    expect(screen.getByTestId('clone-a1')).toBeInTheDocument()
    expect(screen.getByTitle('Modifier')).toBeInTheDocument()
    expect(screen.getByTitle('Supprimer')).toBeInTheDocument()
    // Dernière exécution (nouvelle colonne, code en cyan si succès)
    expect(screen.getByTestId('last-run-a1')).toHaveTextContent('200')
  })

  it('pending_count > 0 → badge magenta « n en attente »', async () => {
    vi.mocked(automationsApi.list).mockResolvedValue([makeAuto({ pending_count: 3 })])
    renderPage()
    const badge = await screen.findByTestId('pending-a1')
    expect(badge).toHaveTextContent('3 en attente')
    expect(badge).toHaveClass('tag-accent-2')
  })

  it('les commandes du curseur appellent la bonne API', async () => {
    vi.mocked(automationsApi.runNext).mockResolvedValue({ status: 'no_pending' })
    vi.mocked(automationsApi.advance).mockResolvedValue({ status: 'no_pending' })
    vi.mocked(automationsApi.cursorBack).mockResolvedValue({ cursor: 0 })
    vi.mocked(automationsApi.clone).mockResolvedValue(makeAuto({ id: 'a2', label: 'Vers RAG (copie)' }))
    renderPage()
    fireEvent.click(await screen.findByTestId('run-next-a1'))
    await waitFor(() => expect(automationsApi.runNext).toHaveBeenCalledWith('ws1', 'a1'))
    fireEvent.click(screen.getByTestId('advance-a1'))
    await waitFor(() => expect(automationsApi.advance).toHaveBeenCalledWith('ws1', 'a1'))
    fireEvent.click(screen.getByTestId('cursor-back-a1'))
    await waitFor(() => expect(automationsApi.cursorBack).toHaveBeenCalledWith('ws1', 'a1'))
    fireEvent.click(screen.getByTestId('clone-a1'))
    await waitFor(() => expect(automationsApi.clone).toHaveBeenCalledWith('ws1', 'a1'))
  })

  it('suppression : ConfirmDialog avec verbe explicite (plus de window.confirm)', async () => {
    vi.mocked(automationsApi.delete).mockResolvedValue(undefined as never)
    renderPage()
    fireEvent.click(await screen.findByTitle('Supprimer'))
    const dialog = await screen.findByTestId('delete-auto-dialog')
    expect(dialog).toHaveTextContent('Vers RAG')
    fireEvent.click(screen.getByTestId('delete-auto-dialog-confirm'))
    await waitFor(() => expect(automationsApi.delete).toHaveBeenCalledWith('ws1', 'a1'))
  })

  it('détail déplié : URL, template de corps, historique et vidage confirmé', async () => {
    vi.mocked(automationsApi.clearRuns).mockResolvedValue({ deleted: 4 })
    renderPage()
    fireEvent.click(await screen.findByLabelText('Détail de Vers RAG'))
    expect(await screen.findByText('https://rag.example/api')).toBeInTheDocument()
    expect(screen.getByText('{"doc": "{title}"}')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('clear-runs-a1'))
    fireEvent.click(await screen.findByTestId('clear-runs-dialog-confirm'))
    await waitFor(() => expect(automationsApi.clearRuns).toHaveBeenCalledWith('ws1', 'a1'))
  })

  it('réordonnancement par glisser-déposer, optimiste', async () => {
    vi.mocked(automationsApi.list).mockResolvedValue([
      makeAuto({}), makeAuto({ id: 'a2', label: 'Second', position: 2 }),
    ])
    vi.mocked(automationsApi.reorder).mockResolvedValue([])
    renderPage()
    const first = await screen.findByTestId('auto-card-a1')
    const second = screen.getByTestId('auto-card-a2')
    fireEvent.dragStart(first)
    fireEvent.drop(second)
    await waitFor(() => expect(automationsApi.reorder).toHaveBeenCalledWith('ws1', ['a2', 'a1']))
  })

  it('Push events et Nouvel automate sont en tête de page', async () => {
    renderPage()
    expect(await screen.findByTestId('push-events-btn')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('push-events-btn'))
    expect(await screen.findByTestId('push-events-dialog')).toBeInTheDocument()
  })

  it('état vide : phrase + action de création', async () => {
    vi.mocked(automationsApi.list).mockResolvedValue([])
    renderPage()
    const empty = await screen.findByTestId('no-automations')
    expect(empty.querySelector('button')).not.toBeNull()
  })
})

describe('AutomatesPage — modale (DoD)', () => {
  it('Échap ferme la modale et le focus revient au bouton d’origine', async () => {
    renderPage()
    const editBtn = await screen.findByTitle('Modifier')
    editBtn.focus()
    fireEvent.click(editBtn)
    expect(await screen.findByTestId('auto-dialog-close')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() =>
      expect(screen.queryByTestId('auto-dialog-close')).not.toBeInTheDocument(),
    )
    expect(editBtn).toHaveFocus()
  })

  it('couverture repliée par défaut avec résumé ; refus sans workspace visible hors section', async () => {
    vi.mocked(api.get).mockImplementation((url: string) =>
      Promise.resolve((url === '/workspaces'
        ? [{ slug: 'ws1', label: 'WS 1' }]
        : []) as never),
    )
    renderPage()
    fireEvent.click(await screen.findByTitle('Modifier'))
    fireEvent.click(await screen.findByTestId('auto-tab-events'))
    // Section repliée par défaut, résumé porté sur la ligne.
    const details = document.querySelector('details')
    expect(details?.open).toBe(false)
    expect(details).toHaveTextContent('1 workspace · tous les blocs')
    // Décocher le dernier workspace → le refus apparaît HORS de la section,
    // donc visible même repliée (DoD).
    fireEvent.click(details!.querySelector('summary')!)
    const wsCheckbox = await screen.findByTestId('auto-ws-ws1')
    fireEvent.click(wsCheckbox.querySelector('input')!)
    const err = await screen.findByTestId('auto-ws-empty')
    expect(details).not.toContainElement(err)
    expect(err).toHaveTextContent('au moins un workspace')
    // Et l'enregistrement est refusé (bouton verrouillé).
    expect(screen.getByRole('button', { name: 'Enregistrer' })).toBeDisabled()
  })
})
