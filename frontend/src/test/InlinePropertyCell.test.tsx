import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: {
      ...actual.docsApi,
      getDocumentValues: vi.fn(),
      putDocumentValue: vi.fn(),
    },
  }
})

import { docsApi, type AllowedValueOut, type PropertyValueOut } from '../lib/api'
import { InlinePropertyCell } from '../components/InlinePropertyCell'

const statutAllowed: AllowedValueOut[] = [
  { slug: 'a_faire', label: 'À faire', color: '#999', position: 0 },
  { slug: 'done', label: 'Done', color: '#22c55e', position: 1 },
]

function renderCell(over: Partial<React.ComponentProps<typeof InlinePropertyCell>> = {}) {
  const onSaved = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <InlinePropertyCell
        ws="ws"
        docId="d1"
        propSlug="statut"
        propType="restricted_list"
        value={null}
        allowedSlug="a_faire"
        allowedValues={statutAllowed}
        editable
        onSaved={onSaved}
        {...over}
      />
    </QueryClientProvider>,
  )
  return { onSaved }
}

function valueOut(over: Partial<PropertyValueOut>): PropertyValueOut {
  return {
    prop_slug: 'statut',
    prop_label: 'Statut',
    type: 'restricted_list',
    version: 2,
    value: null,
    allowed_value_slug: 'a_faire',
    allowed_value_label: 'À faire',
    required: true,
    behavior: null,
    ...over,
  }
}

describe('InlinePropertyCell', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the read pill for a restricted_list value', () => {
    renderCell()
    expect(screen.getByText('À faire')).toBeInTheDocument()
  })

  it('is not editable when editable=false (no edit control on click)', () => {
    renderCell({ editable: false })
    // Pas de bouton d'édition : le clic ne bascule pas en édition.
    expect(screen.queryByTestId('inline-cell-statut-d1')).not.toBeInTheDocument()
    expect(screen.getByText('À faire')).toBeInTheDocument()
  })

  it('edits a restricted_list value: fetches version, saves the chosen slug, calls onSaved', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([valueOut({ version: 2 })])
    vi.mocked(docsApi.putDocumentValue).mockResolvedValue(valueOut({ version: 3, allowed_value_slug: 'done' }))
    const { onSaved } = renderCell()

    fireEvent.click(screen.getByTestId('inline-cell-statut-d1'))
    // Le contrôle inline apparaît une fois la valeur (et sa version) récupérée.
    await waitFor(() => expect(screen.getByTestId('property-input-statut')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('property-input-statut'), { target: { value: 'done' } })

    await waitFor(() =>
      expect(docsApi.putDocumentValue).toHaveBeenCalledWith('ws', 'd1', 'statut', {
        allowed_value_slug: 'done',
        expected_version: 2,
      }),
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('scopes the select options to the passed (type-scoped) allowed values', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([valueOut({ version: 2 })])
    renderCell()
    fireEvent.click(screen.getByTestId('inline-cell-statut-d1'))
    await waitFor(() => expect(screen.getByTestId('property-input-statut')).toBeInTheDocument())
    const options = Array.from(
      screen.getByTestId('property-input-statut').querySelectorAll('option'),
    ).map((o) => o.textContent)
    // Uniquement les valeurs du type (+ l'option vide), pas une union du bloc.
    expect(options).toContain('À faire')
    expect(options).toContain('Done')
    expect(options).not.toContain('En review')
  })

  it('edits a text value on blur, sending value + version', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      valueOut({ prop_slug: 'nom', prop_label: 'Nom', type: 'text', version: 5, value: 'old', allowed_value_slug: null }),
    ])
    vi.mocked(docsApi.putDocumentValue).mockResolvedValue(
      valueOut({ prop_slug: 'nom', type: 'text', version: 6, value: 'new', allowed_value_slug: null }),
    )
    const { onSaved } = renderCell({
      propSlug: 'nom',
      propType: 'text',
      value: 'old',
      allowedSlug: null,
      allowedValues: [],
    })

    fireEvent.click(screen.getByTestId('inline-cell-nom-d1'))
    await waitFor(() => expect(screen.getByTestId('property-input-nom')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('property-input-nom'), { target: { value: 'new' } })
    fireEvent.blur(screen.getByTestId('property-input-nom'))

    await waitFor(() =>
      expect(docsApi.putDocumentValue).toHaveBeenCalledWith('ws', 'd1', 'nom', {
        value: 'new',
        expected_version: 5,
      }),
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })
})
