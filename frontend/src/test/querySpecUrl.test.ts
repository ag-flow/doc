import { describe, it, expect } from 'vitest'
import { readUrlState, writeUrlState } from '../lib/querySpecUrl'

describe('querySpecUrl', () => {
  it('aller-retour d’un tri multi-clé et de filtres', () => {
    const state = {
      spec: {
        filters: [
          { prop: 'statut', op: 'in' as const, values: ['en_cours', 'fait'] },
          { prop: 'poids', op: 'between' as const, values: ['3', '8'] },
          { prop: 'titre', op: 'contains' as const, value: 'socle' },
        ],
        sort: [
          { key: 'statut', dir: 'asc' as const },
          { key: 'title', dir: 'desc' as const },
        ],
        page: 3,
      },
      treeMode: false,
    }
    const params = writeUrlState(state)
    expect(params.get('sort')).toBe('statut:asc,title:desc')
    expect(params.getAll('f')).toEqual([
      'statut:in:en_cours|fait',
      'poids:between:3|8',
      'titre:contains:socle',
    ])
    expect(readUrlState(params)).toEqual(state)
  })

  it('une URL vierge ne porte aucun paramètre', () => {
    const params = writeUrlState({ spec: { filters: [], sort: [], page: 1 }, treeMode: true })
    expect([...params.keys()]).toEqual([])
  })

  it('valeurs contenant les séparateurs : échappées, jamais cassées', () => {
    const state = {
      spec: {
        filters: [{ prop: 'a:b', op: 'eq' as const, value: 'x|y,z~w' }],
        sort: [],
        page: 1,
      },
      treeMode: true,
    }
    const round = readUrlState(writeUrlState(state))
    expect(round.spec.filters[0]).toEqual({ prop: 'a:b', op: 'eq', value: 'x|y,z~w' })
  })

  it('paramètres illisibles ignorés (dégradation, pas de plantage)', () => {
    const params = new URLSearchParams('sort=&f=nimportequoi&f=statut:bidon:x&page=zero')
    expect(readUrlState(params)).toEqual({
      spec: { filters: [], sort: [], page: 1 },
      treeMode: true,
    })
  })
})
