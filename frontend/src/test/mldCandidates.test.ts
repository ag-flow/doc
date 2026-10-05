/** Cibles proposables d'une relation (épic MLD — F7). */

import { describe, it, expect } from 'vitest'
import { entityCandidates, type DocHead } from '../lib/mld/candidates'
import type { TableSchema } from '../lib/mld/adapter'

function head(over: Partial<DocHead> & { doc_technical_key: string }): DocHead {
  return {
    title: over.doc_technical_key,
    parent_id: 'modele-a',
    data_block_ref: 'bloc-1',
    functional_type_slug: 'entity',
    type: 'table-schema',
    ...over,
  }
}

const HEADS: DocHead[] = [
  head({ doc_technical_key: 'bloc-racine', title: 'Modèles', parent_id: null }),
  head({ doc_technical_key: 'modele-a', title: 'Boutique', parent_id: 'bloc-racine', functional_type_slug: 'model', type: 'model-layout' }),
  head({ doc_technical_key: 'modele-b', title: 'Facturation', parent_id: 'bloc-racine', functional_type_slug: 'model', type: 'model-layout' }),
  head({ doc_technical_key: 'commande', title: 'Commande' }),
  head({ doc_technical_key: 'client', title: 'Client' }),
  head({ doc_technical_key: 'facture', title: 'Facture', parent_id: 'modele-b' }),
]

const SCHEMAS = new Map<string, TableSchema>([
  ['commande', { name: 'commande', fields: [{ name: 'id' }, { name: 'client_id', title: 'Client' }] }],
  ['client', { name: 'client', fields: [{ name: 'id' }] }],
  ['facture', { name: 'facture', fields: [{ name: 'id' }] }],
])

describe('entityCandidates', () => {
  it('propose les entités du bloc, avec leur chemin', () => {
    const out = entityCandidates(HEADS, SCHEMAS, 'commande')

    expect(out.map((c) => c.name)).toEqual(['client', 'commande', 'facture'])
    expect(out.find((c) => c.name === 'facture')?.path).toEqual(['Modèles', 'Facturation'])
  })

  it('place le modèle courant en tête', () => {
    // Le cas nominal est de relier deux entités du même modèle : il ne doit pas
    // se retrouver noyé sous les autres.
    const out = entityCandidates(HEADS, SCHEMAS, 'commande')
    expect(out.filter((c) => c.sameModel).map((c) => c.name)).toEqual(['client', 'commande'])
    expect(out[out.length - 1].name).toBe('facture')
  })

  it('n\'exclut pas l\'entité courante — une relation réflexive est légitime', () => {
    // Une catégorie qui a une catégorie parente se déclare sur elle-même.
    expect(entityCandidates(HEADS, SCHEMAS, 'commande').map((c) => c.name)).toContain('commande')
  })

  it('remonte les champs de chaque cible', () => {
    const commande = entityCandidates(HEADS, SCHEMAS, 'client').find((c) => c.name === 'commande')
    expect(commande?.fields).toEqual([
      { name: 'id', title: undefined },
      { name: 'client_id', title: 'Client' },
    ])
  })

  it('écarte les documents d\'un AUTRE bloc', () => {
    const ailleurs = [...HEADS, head({ doc_technical_key: 'autre', title: 'Autre', data_block_ref: 'bloc-2' })]
    const schemas = new Map(SCHEMAS).set('autre', { name: 'autre' })
    expect(entityCandidates(ailleurs, schemas, 'commande').map((c) => c.name)).not.toContain('autre')
  })

  it('écarte les documents d\'un autre type fonctionnel ou d\'un autre type de contenu', () => {
    // Les modèles eux-mêmes sont dans le bloc : ils ne sont pas des cibles.
    expect(entityCandidates(HEADS, SCHEMAS, 'commande').map((c) => c.docId)).not.toContain('modele-b')
  })

  it('écarte une entité sans `name` — elle serait indésignable', () => {
    const schemas = new Map(SCHEMAS)
    schemas.set('facture', { fields: [] })
    expect(entityCandidates(HEADS, schemas, 'commande').map((c) => c.name)).not.toContain('facture')
  })

  it('rend une liste vide si l\'entité courante est inconnue', () => {
    expect(entityCandidates(HEADS, SCHEMAS, 'fantome')).toEqual([])
  })

  it('tronque un chemin cyclique au lieu de boucler', () => {
    const cycle: DocHead[] = [
      head({ doc_technical_key: 'a', title: 'A', parent_id: 'b' }),
      head({ doc_technical_key: 'b', title: 'B', parent_id: 'a' }),
    ]
    const schemas = new Map<string, TableSchema>([['a', { name: 'a' }], ['b', { name: 'b' }]])
    expect(() => entityCandidates(cycle, schemas, 'a')).not.toThrow()
  })
})
