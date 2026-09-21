/** Tuilage d'un plan en pages (épic MLD — F4d). */

import { describe, it, expect } from 'vitest'
import { tileGrid } from '../lib/print/layout'

describe('tileGrid', () => {
  it('couvre le point le plus en bas à droite', () => {
    // 250×150 dans des pages de 100×100 → 3 colonnes, 2 lignes. Le reste de la
    // dernière colonne et de la dernière ligne est vide : c'est attendu.
    const tiles = tileGrid(250, 150, 100, 100)
    expect(tiles).toHaveLength(6)
    expect(Math.max(...tiles.map((t) => t.col))).toBe(3)
    expect(Math.max(...tiles.map((t) => t.row))).toBe(2)
  })

  it('parcourt COLONNE par colonne, pas ligne par ligne', () => {
    // On descend la première colonne jusqu'en bas avant de passer à la suivante.
    const order = tileGrid(200, 300, 100, 100).map((t) => `${t.col}:${t.row}`)
    expect(order).toEqual(['1:1', '1:2', '1:3', '2:1', '2:2', '2:3'])
  })

  it('décale le contenu de la taille d\'une page par tuile', () => {
    const tiles = tileGrid(200, 200, 100, 100)
    expect(tiles.find((t) => t.col === 2 && t.row === 2)).toEqual({
      col: 2, row: 2, x: 100, y: 100,
    })
    // La première tuile montre le contenu sans décalage : origine en haut à gauche.
    expect(tiles[0]).toEqual({ col: 1, row: 1, x: 0, y: 0 })
  })

  it('dégénère en tranchage VERTICAL quand le contenu tient en largeur', () => {
    // C'est ce qui rend ce régime sûr comme repli universel : un texte long
    // s'imprime correctement sans que sa surface ait rien à déclarer.
    const tiles = tileGrid(80, 350, 100, 100)
    expect(tiles.every((t) => t.col === 1)).toBe(true)
    expect(tiles).toHaveLength(4)
  })

  it('un contenu plus petit qu\'une page tient sur une seule tuile', () => {
    expect(tileGrid(50, 50, 100, 100)).toEqual([{ col: 1, row: 1, x: 0, y: 0 }])
  })

  it('une taille nulle ou négative ne produit aucune tuile', () => {
    // Un document vide n'a rien à imprimer — surtout pas une page blanche.
    expect(tileGrid(0, 100, 100, 100)).toEqual([])
    expect(tileGrid(100, 0, 100, 100)).toEqual([])
    expect(tileGrid(100, 100, 0, 100)).toEqual([])
  })

  it('une dimension à peine supérieure à une page en ajoute une seule', () => {
    // Garde-fou d'arrondi : 100.5 ne doit pas produire trois colonnes.
    expect(Math.max(...tileGrid(100.5, 100, 100, 100).map((t) => t.col))).toBe(2)
  })
})
