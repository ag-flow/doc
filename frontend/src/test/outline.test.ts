import { describe, it, expect } from 'vitest'
import { parseOutline, countNodes, maxDepth } from '../lib/blockCodecs/outline'

describe('parseOutline', () => {
  it('construit un arbre depuis l’indentation (2 espaces = 1 niveau)', () => {
    const { roots } = parseOutline('Racine\n  Enfant 1\n    Petit\n  Enfant 2')
    expect(roots).toHaveLength(1)
    expect(roots[0].label).toBe('Racine')
    expect(roots[0].children.map((c) => c.label)).toEqual(['Enfant 1', 'Enfant 2'])
    expect(roots[0].children[0].children[0].label).toBe('Petit')
  })

  it('traite les tabulations comme un niveau', () => {
    const { roots } = parseOutline('A\n\tB\n\t\tC')
    expect(roots[0].children[0].label).toBe('B')
    expect(roots[0].children[0].children[0].label).toBe('C')
  })

  it('sépare « label | note »', () => {
    const { roots } = parseOutline('Service | v2')
    expect(roots[0].label).toBe('Service')
    expect(roots[0].note).toBe('v2')
  })

  it('supporte plusieurs racines (forêt)', () => {
    const { roots } = parseOutline('A\nB\n  B1')
    expect(roots.map((r) => r.label)).toEqual(['A', 'B'])
    expect(roots[1].children[0].label).toBe('B1')
  })

  it('rattache un saut de profondeur sans erreur', () => {
    // « Petit » saute directement à la profondeur 2 sous une racine à 0.
    const { roots } = parseOutline('Racine\n    Petit')
    expect(roots[0].children[0].label).toBe('Petit')
  })

  it('ignore les lignes vides ; countNodes / maxDepth', () => {
    const { roots } = parseOutline('A\n\n  B\n  C\n')
    expect(countNodes(roots)).toBe(3)
    expect(maxDepth(roots)).toBe(2)
  })
})
