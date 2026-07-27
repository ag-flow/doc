import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import '../lib/i18n'
import { EmptyState, ErrorLine, SheetSkeleton, TableSkeleton } from '../components/ui/states'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Button } from '../components/ui/button'

describe('états transverses — vides, chargement, erreurs', () => {
  it('état vide : une phrase, une action, aucun encadré ni illustration', () => {
    const { container } = render(
      <EmptyState testId="empty" message="Aucun workspace." action={<Button>Créer</Button>} />,
    )
    const empty = screen.getByTestId('empty')
    expect(empty).toHaveTextContent('Aucun workspace.')
    expect(screen.getByRole('button', { name: 'Créer' })).toBeInTheDocument()
    // Ni image, ni bordure : le blanc porte le message.
    expect(container.querySelector('img, svg')).toBeNull()
    expect(empty.className).not.toMatch(/border|card/)
  })

  it('squelette de table : dimensions réelles, annoncé comme occupé, jamais un spinner', () => {
    render(<TableSkeleton rows={3} columns={2} />)
    const sk = screen.getByTestId('table-skeleton')
    expect(sk).toHaveAttribute('aria-busy', 'true')
    expect(sk).toHaveAttribute('role', 'status')
    // Une ligne de squelette par ligne attendue.
    expect(sk.children).toHaveLength(4) // 3 lignes + le libellé lecteur d'écran
    expect(sk.querySelectorAll('.animate-pulse')).toHaveLength(6)
  })

  it('squelette de feuille : un titre et des lignes de texte', () => {
    render(<SheetSkeleton />)
    const sk = screen.getByTestId('sheet-skeleton')
    expect(sk.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(5)
  })

  it('erreur de page : une ligne magenta dans une région aria-live permanente', () => {
    const { container, rerender } = render(<ErrorLine message={null} />)
    const region = container.querySelector('[aria-live="polite"]')
    // La région préexiste au message, sinon son apparition n'est pas annoncée.
    expect(region).not.toBeNull()
    expect(screen.queryByTestId('error-line')).not.toBeInTheDocument()

    rerender(<ErrorLine message="Échec de l’enregistrement" />)
    const line = screen.getByTestId('error-line')
    expect(line).toHaveClass('text-accent-2-700')
    expect(container.querySelector('[aria-live="polite"]')).toContainElement(line)
  })
})

describe('confirmation destructive', () => {
  function setup(over: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Supprimer le bloc"
        message="Cette action est irréversible."
        confirmLabel="Supprimer le bloc"
        impactMessage="Ce bloc contient 7 documents."
        onConfirm={onConfirm}
        onCancel={onCancel}
        {...over}
      />,
    )
    return { onConfirm, onCancel }
  }

  it('annonce l’impact et porte un verbe explicite dans le bouton', () => {
    setup()
    expect(screen.getByTestId('confirm-dialog-impact')).toHaveTextContent('7 documents')
    expect(screen.getByTestId('confirm-dialog-confirm')).toHaveTextContent('Supprimer le bloc')
    // Pas de bouton « OK » ambigu.
    expect(screen.queryByRole('button', { name: 'OK' })).not.toBeInTheDocument()
  })

  it('le focus part sur Annuler, pas sur l’action destructrice', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Annuler' })).toHaveFocus()
  })

  it('Échap annule', () => {
    const { onCancel } = setup()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('Tab tourne dans le dialogue (aucune fuite de focus vers la page)', () => {
    setup()
    const cancel = screen.getByRole('button', { name: 'Annuler' })
    const confirm = screen.getByTestId('confirm-dialog-confirm')
    confirm.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(cancel).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(confirm).toHaveFocus()
  })

  it('confirmation verrouillée : le bouton reste inactif', () => {
    const { onConfirm } = setup({ confirmDisabled: true })
    const confirm = screen.getByTestId('confirm-dialog-confirm')
    expect(confirm).toBeDisabled()
    fireEvent.click(confirm)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('le dialogue est un vrai dialogue modal, nommé par son titre', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('Supprimer le bloc')
  })
})

// ── Audit clavier (garde-fous automatisables) ────────────────────────────────

const SRC_DIRS = ['src/pages', 'src/components', 'src/components/ui']

function sourceFiles(): { file: string; src: string }[] {
  const out: { file: string; src: string }[] = []
  for (const dir of SRC_DIRS) {
    const abs = join(process.cwd(), dir)
    for (const f of readdirSync(abs)) {
      if (f.endsWith('.tsx')) out.push({ file: `${dir}/${f}`, src: readFileSync(join(abs, f), 'utf-8') })
    }
  }
  return out
}

describe('audit clavier', () => {
  it('aucune action révélée au survol seul (sinon elle est inatteignable au clavier)', () => {
    const offenders = sourceFiles()
      .filter(({ src }) => {
        // Un bloc `opacity-0` révélé par `group-hover` doit AUSSI l'être par
        // `focus-within`, sinon la navigation clavier ne peut jamais l'atteindre.
        const hoverReveals = src.match(/opacity-0[^"'`]*group-hover:opacity-100/g) ?? []
        return hoverReveals.some((m) => !m.includes('focus-within:opacity-100'))
          && !/focus-within:opacity-100/.test(src)
      })
      .map(({ file }) => file)
    expect(offenders).toEqual([])
  })

  it('le focus clavier est stylé globalement et le focus natif n’est jamais supprimé seul', () => {
    const base = readFileSync(join(process.cwd(), 'src/styles/base.css'), 'utf-8')
    expect(base).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--color-accent\)/)
    // `outline: none` n'est admis que sur `:focus` (le clavier passe par :focus-visible).
    const suppressions = [...base.matchAll(/([^{}]+)\{[^}]*outline:\s*none/g)]
      // On garde le dernier sélecteur du groupe capturé : les commentaires CSS
      // qui précèdent la règle font partie du texte, pas du sélecteur.
      .map((m) => m[1].split('\n').pop()!.trim())
    expect(suppressions).toEqual([':focus'])
  })

  it('les dialogues du système piègent le focus et se ferment par Échap', () => {
    const confirm = readFileSync(join(process.cwd(), 'src/components/ConfirmDialog.tsx'), 'utf-8')
    expect(confirm).toMatch(/e\.key === 'Escape'/)
    expect(confirm).toMatch(/e\.key !== 'Tab'/)
  })
})
