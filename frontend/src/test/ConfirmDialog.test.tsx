import { describe, it, expect } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '../lib/i18n'
import { ConfirmDialog } from '../components/ConfirmDialog'

/** Reproduit la modale de suppression de workspace : un champ de garde contrôlé,
 *  et des closures onConfirm/onCancel RECRÉÉES à chaque rendu du parent. */
function Harness() {
  const [v, setV] = useState('')
  return (
    <ConfirmDialog
      title="Supprimer ?"
      confirmLabel="Supprimer"
      message={
        <input
          data-testid="guard"
          value={v}
          onChange={(e) => setV(e.target.value)}
          autoFocus
        />
      }
      onConfirm={() => undefined}
      onCancel={() => undefined}
      testId="dlg"
    />
  )
}

describe('ConfirmDialog — focus', () => {
  it('le focus initial va sur « Annuler » (Entrée réflexe ne détruit pas)', () => {
    render(<Harness />)
    expect(screen.getByText('Annuler')).toHaveFocus()
  })

  it('le champ de garde garde le focus à chaque frappe (pas de vol vers Annuler)', () => {
    render(<Harness />)
    const guard = screen.getByTestId('guard')
    guard.focus()
    expect(guard).toHaveFocus()

    // Chaque frappe re-render le parent (nouvelle closure onCancel) : le focus
    // ne doit PAS repartir sur « Annuler ».
    fireEvent.change(guard, { target: { value: 'c' } })
    expect(guard).toHaveFocus()
    fireEvent.change(guard, { target: { value: 'ca' } })
    expect(guard).toHaveFocus()
    fireEvent.change(guard, { target: { value: 'cap' } })
    expect(guard).toHaveFocus()
  })
})
