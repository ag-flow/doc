import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen } from '@testing-library/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Tag } from '../components/ui/tag'
import { Field } from '../components/ui/field'
import { DesignSystemPage } from '../pages/DesignSystemPage'

const STYLES = join(process.cwd(), 'src/styles')
const UI = join(process.cwd(), 'src/components/ui')

/** Une couleur écrite en dur : hex, rgb() ou hsl(). Les tokens font foi. */
const HARDCODED_COLOR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/

describe('socle Broadsheet — les primitives portent les classes du système', () => {
  it('bouton : variants et états', () => {
    const { container } = render(
      <>
        <Button>ok</Button>
        <Button variant="secondary">sec</Button>
        <Button variant="ghost">ghost</Button>
        <Button variant="danger">danger</Button>
        <Button variant="icon" aria-label="ic" />
        <Button size="sm">sm</Button>
        <Button block>block</Button>
      </>,
    )
    const cls = [...container.querySelectorAll('button')].map((b) => b.className)
    expect(cls.every((c) => c.includes('btn'))).toBe(true)
    expect(cls[0]).toContain('btn-primary')
    expect(cls[1]).toContain('btn-secondary')
    expect(cls[2]).toContain('btn-ghost')
    expect(cls[3]).toContain('btn-danger')
    expect(cls[4]).toContain('btn-icon')
    expect(cls[5]).toContain('btn-sm')
    expect(cls[6]).toContain('btn-block')
  })

  it('champ : classe .input et invalidité accessible', () => {
    render(<Input aria-invalid="true" placeholder="x" />)
    const input = screen.getByPlaceholderText('x')
    expect(input.className).toContain('input')
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('field : l’erreur remplace l’aide et porte role=alert', () => {
    const { rerender } = render(
      <Field label="L" hint="aide"><Input /></Field>,
    )
    expect(screen.getByText('aide')).toBeInTheDocument()
    rerender(<Field label="L" hint="aide" error="raté"><Input /></Field>)
    expect(screen.queryByText('aide')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('raté')
  })

  it('tag : un variant = une classe du système', () => {
    const { container } = render(
      <>
        <Tag variant="accent">a</Tag>
        <Tag variant="accent-2">b</Tag>
        <Tag variant="neutral">c</Tag>
        <Tag variant="outline">d</Tag>
      </>,
    )
    const cls = [...container.querySelectorAll('span')].map((s) => s.className)
    expect(cls).toEqual([
      'tag tag-accent',
      'tag tag-accent-2',
      'tag tag-neutral',
      'tag tag-outline',
    ])
  })
})

describe('socle Broadsheet — page de démonstration', () => {
  it('rend chaque famille de primitives (référence de recette)', () => {
    const { container } = render(<DesignSystemPage />)
    for (const cls of ['btn-primary', 'btn-danger', 'input', 'tag-accent', 'card', 'table', 'seg', 'radio']) {
      expect(container.querySelector(`.${cls}`), cls).not.toBeNull()
    }
    expect(screen.getByRole('heading', { level: 1, name: 'Broadsheet' })).toBeInTheDocument()
  })
})

describe('socle Broadsheet — aucune valeur en dur hors du fichier de tokens', () => {
  it('seul tokens.css déclare des couleurs littérales', () => {
    const offenders = readdirSync(STYLES)
      .filter((f) => f.endsWith('.css') && f !== 'tokens.css')
      .filter((f) => HARDCODED_COLOR.test(readFileSync(join(STYLES, f), 'utf-8')))
    expect(offenders).toEqual([])
  })

  it('aucun nom de police en dur hors tokens.css', () => {
    const offenders = readdirSync(STYLES)
      .filter((f) => f.endsWith('.css') && f !== 'tokens.css')
      .filter((f) => /font-family:(?!\s*var\()/.test(readFileSync(join(STYLES, f), 'utf-8')))
    expect(offenders).toEqual([])
  })

  it('les primitives ui/ ne contiennent ni couleur ni police littérale', () => {
    const offenders = readdirSync(UI)
      .filter((f) => f.endsWith('.tsx'))
      .filter((f) => {
        const src = readFileSync(join(UI, f), 'utf-8')
        return HARDCODED_COLOR.test(src) || /font-family/.test(src)
      })
    expect(offenders).toEqual([])
  })
})
