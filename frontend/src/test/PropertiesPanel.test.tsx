import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
    docsApi: {
      ...actual.docsApi,
      getDocumentValues: vi.fn(),
      putDocumentValue: vi.fn(),
    },
    ApiError: actual.ApiError,
  }
})

import { api, docsApi, ApiError, type PropertyValueOut } from '../lib/api'
import { PropertiesPanel } from '../components/PropertiesPanel'

const baseValues: PropertyValueOut[] = [
  {
    prop_slug: 'title2',
    prop_label: 'Sous-titre',
    type: 'text',
    version: 1,
    value: 'Bonjour',
    allowed_value_slug: null,
    allowed_value_label: null,
    required: false,
      behavior: null,
  },
  {
    prop_slug: 'status',
    prop_label: 'Statut',
    type: 'restricted_list',
    version: 1,
    value: null,
    allowed_value_slug: 'todo',
    allowed_value_label: 'À faire',
    required: true,
  behavior: null,
  },
]

const richTypes = [
  {
    slug: 'epic',
    label: 'Epic',
    properties: [
      {
        slug: 'status',
        label: 'Statut',
        type: 'restricted_list',
        required: true,
  behavior: null,
        allowed_values: [
          { slug: 'todo', label: 'À faire', color: '#3b82f6', position: 0 },
          { slug: 'done', label: 'Terminé', color: '#22c55e', position: 1 },
        ],
      },
    ],
  },
]

function renderPanel(functionalTypeSlug: string | null = 'epic') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PropertiesPanel ws="ws" docId="d1" functionalTypeSlug={functionalTypeSlug} />
    </QueryClientProvider>,
  )
}

describe('PropertiesPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  // DoD 25.1 — rendu des champs
  it('renders fields for each property', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue(baseValues)
    vi.mocked(api.get).mockResolvedValue(richTypes)

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-title2')).toBeInTheDocument())
    expect(screen.getByTestId('property-status')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Bonjour')).toBeInTheDocument()
  })

  // DoD 25.2 — statut en select avec pastille couleur
  it('shows restricted_list as select and color pill', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue(baseValues)
    vi.mocked(api.get).mockResolvedValue(richTypes)

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-status')).toBeInTheDocument())
    expect(screen.getByTestId('property-input-status')).toBeInTheDocument()
    // Pastille couleur visible car todo est sélectionné
    await waitFor(() => expect(screen.getByTestId('property-pill-status')).toBeInTheDocument())
    expect(screen.getByTestId('property-pill-status').textContent).toBe('À faire')
  })

  // DoD 25.3 — budget_jours = -1 → 422 → message erreur
  it('shows error on 422 (invalid value)', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'budget',
        prop_label: 'Budget',
        type: 'int',
        version: 1,
        value: '5',
        allowed_value_slug: null,
        allowed_value_label: null,
        required: false,
      behavior: null,
      },
    ])
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(docsApi.putDocumentValue).mockRejectedValue(
      new ApiError(422, 'La valeur doit être positive', 'La valeur doit être positive'),
    )

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-budget')).toBeInTheDocument())

    const input = screen.getByTestId('property-input-budget')
    fireEvent.change(input, { target: { value: '-1' } })
    await act(async () => {
      fireEvent.blur(input)
    })

    await waitFor(() =>
      expect(screen.getByTestId('property-error-budget')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('property-error-budget').textContent).toContain(
      'La valeur doit être positive',
    )
  })

  // DoD 25.4 — 409 → encart conflit → "Garder ma valeur" → resave réussit
  it('shows conflict encart on 409 and resolves with keepMine', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'budget',
        prop_label: 'Budget',
        type: 'int',
        version: 1,
        value: '5',
        allowed_value_slug: null,
        allowed_value_label: null,
        required: false,
      behavior: null,
      },
    ])
    vi.mocked(api.get).mockResolvedValue([])

    const conflictDetail = { version: 2, value: '99', allowed_value_slug: null }
    const savedValue: PropertyValueOut = {
      prop_slug: 'budget',
      prop_label: 'Budget',
      type: 'int',
      version: 3,
      value: '7',
      allowed_value_slug: null,
      allowed_value_label: null,
      required: false,
      behavior: null,
    }

    // Premier appel → 409, deuxième → succès
    vi.mocked(docsApi.putDocumentValue)
      .mockRejectedValueOnce(new ApiError(409, conflictDetail, 'Conflit'))
      .mockResolvedValueOnce(savedValue)

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-budget')).toBeInTheDocument())

    const input = screen.getByTestId('property-input-budget')
    fireEvent.change(input, { target: { value: '7' } })
    await act(async () => {
      fireEvent.blur(input)
    })

    // Encart conflit visible
    await waitFor(() =>
      expect(screen.getByTestId('property-conflict-budget')).toBeInTheDocument(),
    )

    // Cliquer "Garder le mien"
    fireEvent.click(screen.getByText('Garder le mien'))

    // Conflit résolu, putDocumentValue appelé une deuxième fois
    await waitFor(() =>
      expect(vi.mocked(docsApi.putDocumentValue)).toHaveBeenCalledTimes(2),
    )
    expect(screen.queryByTestId('property-conflict-budget')).not.toBeInTheDocument()
  })

  // DoD 25.5 — deux champs indépendants : conflit sur l'un n'affecte pas l'autre
  it('conflict on one field does not affect sibling field', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'budget',
        prop_label: 'Budget',
        type: 'int',
        version: 1,
        value: '5',
        allowed_value_slug: null,
        allowed_value_label: null,
        required: false,
      behavior: null,
      },
      {
        prop_slug: 'title2',
        prop_label: 'Sous-titre',
        type: 'text',
        version: 1,
        value: 'Hello',
        allowed_value_slug: null,
        allowed_value_label: null,
        required: false,
      behavior: null,
      },
    ])
    vi.mocked(api.get).mockResolvedValue([])

    const conflictDetail = { version: 2, value: '99', allowed_value_slug: null }
    vi.mocked(docsApi.putDocumentValue).mockRejectedValueOnce(
      new ApiError(409, conflictDetail, 'Conflit'),
    )

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-budget')).toBeInTheDocument())

    const budgetInput = screen.getByTestId('property-input-budget')
    fireEvent.change(budgetInput, { target: { value: '7' } })
    await act(async () => {
      fireEvent.blur(budgetInput)
    })

    // Conflit sur budget
    await waitFor(() =>
      expect(screen.getByTestId('property-conflict-budget')).toBeInTheDocument(),
    )
    // title2 n'est pas en état conflit
    expect(screen.queryByTestId('property-conflict-title2')).not.toBeInTheDocument()
    // title2 reste éditable
    expect(screen.getByTestId('property-input-title2')).not.toBeDisabled()
  })

  // Régression : un statut à valeur par défaut (version null, jamais écrit
  // explicitement) doit s'enregistrer avec expected_version 0 — sinon le
  // backend rejette (« Input should be a valid integer ») et le statut par
  // défaut est impossible à changer.
  it('saves a default-only restricted_list with expected_version 0', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'status',
        prop_label: 'Statut',
        type: 'restricted_list',
        version: null, // aucune valeur explicite : seul le défaut du type
        value: null,
        allowed_value_slug: 'todo',
        allowed_value_label: 'À faire',
        required: true,
        behavior: null,
      },
    ])
    vi.mocked(api.get).mockResolvedValue(richTypes)
    vi.mocked(docsApi.putDocumentValue).mockResolvedValue({
      prop_slug: 'status',
      prop_label: 'Statut',
      type: 'restricted_list',
      version: 1,
      value: null,
      allowed_value_slug: 'done',
      allowed_value_label: 'Terminé',
      required: true,
      behavior: null,
    })

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-input-status')).toBeInTheDocument())

    const select = screen.getByTestId('property-input-status')
    fireEvent.change(select, { target: { value: 'done' } })
    await act(async () => {
      fireEvent.blur(select)
    })

    await waitFor(() => expect(vi.mocked(docsApi.putDocumentValue)).toHaveBeenCalled())
    expect(vi.mocked(docsApi.putDocumentValue)).toHaveBeenCalledWith(
      'ws',
      'd1',
      'status',
      { allowed_value_slug: 'done', expected_version: 0 },
    )
    // Aucune erreur affichée.
    expect(screen.queryByTestId('property-error-status')).not.toBeInTheDocument()
  })

  // Régression : deux types partagent le slug `status` avec des valeurs autorisées
  // DIFFÉRENTES. Le select d'un document doit présenter les options de SON type,
  // pas celles d'un autre type (sinon on envoie un slug étranger → 422 « valeur
  // autorisée introuvable » sur une liste fermée).
  it('scopes allowed values to the document type on slug collision', async () => {
    const collidingTypes = [
      {
        slug: 'article',
        label: 'Article',
        properties: [
          {
            slug: 'status',
            label: 'Statut',
            type: 'restricted_list',
            required: true,
            behavior: null,
            allowed_values: [
              { slug: 'brouillon', label: 'Brouillon', color: null, position: 0 },
              { slug: 'publie', label: 'Publiée', color: '#22c55e', position: 1 },
            ],
          },
        ],
      },
      // Type balayé EN DERNIER : sans scoping, il écraserait l'index pour `status`.
      {
        slug: 'epic',
        label: 'Epic',
        properties: [
          {
            slug: 'status',
            label: 'Statut',
            type: 'restricted_list',
            required: true,
            behavior: null,
            allowed_values: [
              { slug: 'todo', label: 'À faire', color: '#3b82f6', position: 0 },
              { slug: 'done', label: 'Terminé', color: '#22c55e', position: 1 },
            ],
          },
        ],
      },
    ]
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'status',
        prop_label: 'Statut',
        type: 'restricted_list',
        version: 1,
        value: null,
        allowed_value_slug: 'publie',
        allowed_value_label: 'Publiée',
        required: true,
        behavior: null,
      },
    ])
    vi.mocked(api.get).mockResolvedValue(collidingTypes)

    renderPanel('article')
    await waitFor(() => expect(screen.getByTestId('property-input-status')).toBeInTheDocument())

    const select = screen.getByTestId('property-input-status') as HTMLSelectElement
    const optionValues = Array.from(select.options).map((o) => o.value)
    // Doit contenir les valeurs d'`article`, pas celles d'`epic`.
    expect(optionValues).toContain('publie')
    expect(optionValues).toContain('brouillon')
    expect(optionValues).not.toContain('todo')
    expect(optionValues).not.toContain('done')
  })

  // État vide
  it('shows empty message when no properties', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([])
    vi.mocked(api.get).mockResolvedValue([])
    renderPanel()
    await waitFor(() => expect(screen.getByText('Aucune propriété')).toBeInTheDocument())
  })
})
