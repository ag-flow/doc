import { describe, it, expect } from 'vitest'
import {
  isDisplayBody,
  parseDisplay,
  MAX_COMPONENTS,
} from '../lib/blockCodecs/displayParse'

const ADR_SAMPLE = JSON.stringify([
  { id: 'root', component: 'Column', children: ['title', 'cards'] },
  { id: 'title', component: 'Text', text: 'Comparatif', hint: 'h2' },
  { id: 'cards', component: 'Row', children: ['c1', 'c2'] },
  { id: 'c1', component: 'Card', children: ['c1t'] },
  { id: 'c1t', component: 'Text', text: 'Option A', hint: 'h3' },
  { id: 'c2', component: 'Card', children: ['c2t'] },
  { id: 'c2t', component: 'Text', text: 'Option B', hint: 'h3' },
])

describe('isDisplayBody (rejet de l’alias ```display)', () => {
  it('tableau JSON non vide → candidat', () => {
    expect(isDisplayBody(ADR_SAMPLE)).toBe(true)
  })
  it('non-JSON, objet, tableau vide → écarté', () => {
    expect(isDisplayBody('const x = display();')).toBe(false)
    expect(isDisplayBody('{"id": "root"}')).toBe(false)
    expect(isDisplayBody('[]')).toBe(false)
  })
})

describe('parseDisplay — arbre', () => {
  it('résout l’exemple de l’ADR : racine root, refs par id, props à plat', () => {
    const { root, diagnostics } = parseDisplay(ADR_SAMPLE)
    expect(root?.component).toBe('Column')
    expect(root?.children.map((c) => c.id)).toEqual(['title', 'cards'])
    expect(root?.children[0].props).toEqual({ text: 'Comparatif', hint: 'h2' })
    expect(root?.children[1].children).toHaveLength(2)
    expect(diagnostics).toEqual({
      invalid: 0, duplicates: 0, orphans: 0, cut: 0, brokenRefs: 0,
    })
  })

  it('sans id "root" : le premier composant valide devient racine', () => {
    const { root } = parseDisplay(
      '[{"id":"a","component":"Text","text":"x"},{"id":"b","component":"Text","text":"y"}]',
    )
    expect(root?.id).toBe('a')
  })

  it('JSON cassé ou non-tableau → root null, aucun crash', () => {
    expect(parseDisplay('{oops').root).toBeNull()
    expect(parseDisplay('"texte"').root).toBeNull()
  })
})

describe('parseDisplay — diagnostics et gardes', () => {
  it('doublon d’id : le premier gagne, compté', () => {
    const { root, diagnostics } = parseDisplay(
      '[{"id":"root","component":"Text","text":"un"},{"id":"root","component":"Text","text":"deux"}]',
    )
    expect(root?.props.text).toBe('un')
    expect(diagnostics.duplicates).toBe(1)
  })

  it('entrée invalide ignorée + orphelin compté + ref morte comptée', () => {
    const { root, diagnostics } = parseDisplay(JSON.stringify([
      { id: 'root', component: 'Row', children: ['ok', 'fantome'] },
      { id: 'ok', component: 'Text', text: 'là' },
      { component: 'Text', text: 'sans id' },
      { id: 'seul', component: 'Text', text: 'jamais référencé' },
    ]))
    expect(root?.children).toHaveLength(1)
    expect(diagnostics.invalid).toBe(1)
    expect(diagnostics.brokenRefs).toBe(1)
    expect(diagnostics.orphans).toBe(1)
  })

  it('cycle coupé sans boucle infinie', () => {
    const { root, diagnostics } = parseDisplay(JSON.stringify([
      { id: 'root', component: 'Column', children: ['a'] },
      { id: 'a', component: 'Column', children: ['root'] },
    ]))
    expect(root).not.toBeNull()
    expect(diagnostics.cut).toBe(1)
  })

  it('budget de composants borné : rendu partiel + coupes comptées', () => {
    const rootEntry = { id: 'root', component: 'Column', children: [] as string[] }
    const leaves = Array.from({ length: MAX_COMPONENTS + 50 }, (_, i) => ({
      id: `n${i}`, component: 'Text', text: String(i),
    }))
    rootEntry.children = leaves.map((c) => c.id)
    const many = [rootEntry, ...leaves]
    const { root, diagnostics } = parseDisplay(JSON.stringify(many))
    expect(root?.children.length).toBe(MAX_COMPONENTS - 1)
    expect(diagnostics.cut).toBeGreaterThan(0)
  })
})
