import { describe, it, expect } from 'vitest'
import { tokenize, threeWayMerge } from '../lib/merge3'

const BASE = '# Titre\n\nParagraphe un.\n\nParagraphe deux.'

describe('tokenize', () => {
  it('un bloc fence est UN token atomique, le reste est ligne à ligne', () => {
    const md = 'avant\n```df-timeline title="x"\nUn | pas\nDeux | pas\n```\naprès'
    const tokens = tokenize(md)
    expect(tokens).toEqual([
      'avant',
      '```df-timeline title="x"\nUn | pas\nDeux | pas\n```',
      'après',
    ])
    expect(tokens.join('\n')).toBe(md)
  })

  it('fence non fermée : tout jusqu’à la fin devient un token (pas de crash)', () => {
    expect(tokenize('a\n```js\nx')).toEqual(['a', '```js\nx'])
  })
})

describe('threeWayMerge', () => {
  it('zones disjointes → fusion propre des deux côtés, zéro conflit', () => {
    const ours = BASE.replace('Paragraphe un.', 'Paragraphe un ÉDITÉ.')
    const theirs = BASE.replace('Paragraphe deux.', 'Paragraphe deux AGENT.')
    const { merged, conflicts } = threeWayMerge(BASE, ours, theirs)
    expect(conflicts).toBe(0)
    expect(merged).toContain('Paragraphe un ÉDITÉ.')
    expect(merged).toContain('Paragraphe deux AGENT.')
  })

  it('changement identique des deux côtés → pas un conflit', () => {
    const both = BASE.replace('Paragraphe un.', 'Pareil.')
    const { merged, conflicts } = threeWayMerge(BASE, both, both)
    expect(conflicts).toBe(0)
    expect(merged).toBe(both)
  })

  it('même zone modifiée différemment → conflit compté, OURS retenu', () => {
    const ours = BASE.replace('Paragraphe un.', 'Version utilisateur.')
    const theirs = BASE.replace('Paragraphe un.', 'Version agent.')
    const { merged, conflicts } = threeWayMerge(BASE, ours, theirs)
    expect(conflicts).toBe(1)
    expect(merged).toContain('Version utilisateur.')
    expect(merged).not.toContain('Version agent.')
  })

  it('un bloc fence modifié des deux côtés = UN conflit atomique (jamais mélangé)', () => {
    const base = 'intro\n```df-chart type="bar"\nA | 1\nB | 2\n```\nfin'
    const ours = base.replace('A | 1', 'A | 10')
    const theirs = base.replace('B | 2', 'B | 20')
    const { merged, conflicts } = threeWayMerge(base, ours, theirs)
    expect(conflicts).toBe(1)
    // Le bloc retenu est celui de l'utilisateur, INTACT — pas un mélange.
    expect(merged).toContain('```df-chart type="bar"\nA | 10\nB | 2\n```')
  })

  it('theirs seul a bougé → merged = theirs (rien à arbitrer)', () => {
    const theirs = BASE + '\n\nAjout agent.'
    const { merged, conflicts } = threeWayMerge(BASE, BASE, theirs)
    expect(conflicts).toBe(0)
    expect(merged).toBe(theirs)
  })
})
