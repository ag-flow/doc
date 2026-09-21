/** Contrat de pagination déclaré par chaque surface (épic MLD — F4d, pièce B/C). */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  markdownSurface,
  modelLayoutSurface,
  plainTextSurface,
  tableSchemaSurface,
} from '../lib/contentSurfaces'
import { tileColumns, tileGrid } from '../lib/print/layout'

/** jsdom ne met rien en page : on simule la géométrie, seule chose qui compte ici. */
function geometry(rects: Map<Element, { top: number; height: number }>) {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: Element,
  ) {
    const r = rects.get(this) ?? { top: 0, height: 0 }
    return { top: r.top, bottom: r.top + r.height, height: r.height, width: 0, left: 0, right: 0, x: 0, y: r.top, toJSON: () => ({}) } as DOMRect
  })
}

beforeEach(() => vi.restoreAllMocks())

describe('markdownSurface — régime flux', () => {
  it('classe les blocs BlockNote : titre, sécable, insécable', () => {
    const root = document.createElement('div')
    root.innerHTML = `
      <div class="bn-block-outer"><div class="bn-block-content" data-content-type="heading"></div></div>
      <div class="bn-block-outer"><div class="bn-block-content" data-content-type="paragraph"></div></div>
      <div class="bn-block-outer"><div class="bn-block-content" data-content-type="table"></div></div>`
    const outers = root.querySelectorAll('.bn-block-outer')
    geometry(new Map([
      [root, { top: 0, height: 300 }],
      [outers[0], { top: 0, height: 40 }],
      [outers[1], { top: 40, height: 60 }],
      [outers[2], { top: 100, height: 200 }],
    ]))

    const layout = markdownSurface.getPrintLayout!(root)

    expect(layout.mode).toBe('flow')
    expect(layout.mode === 'flow' && layout.blocks.map((b) => b.kind)).toEqual([
      'heading', 'break', 'component',
    ])
  })

  it('ignore les blocs IMBRIQUÉS — seuls les blocs de premier niveau paginent', () => {
    const root = document.createElement('div')
    root.innerHTML = `
      <div class="bn-block-outer"><div class="bn-block-content" data-content-type="bulletListItem"></div>
        <div class="bn-block-outer"><div class="bn-block-content" data-content-type="paragraph"></div></div>
      </div>`
    geometry(new Map())

    const layout = markdownSurface.getPrintLayout!(root)
    expect(layout.mode === 'flow' && layout.blocks).toHaveLength(1)
  })
})

describe('modelLayoutSurface — régime plan', () => {
  it('lit l\'étendue MESURÉE sur le rendu, pas calculée depuis le modèle', () => {
    // Les étiquettes de relation et les cardinalités sont des textes du
    // navigateur, absents du modèle : une étendue calculée les couperait.
    const root = document.createElement('div')
    root.innerHTML = `<div data-print="true" data-content-width="1400" data-content-height="900"></div>`

    expect(modelLayoutSurface.getPrintLayout!(root)).toEqual({
      mode: 'plane', width: 1400, height: 900,
    })
  })

  it('retombe sur la boîte si le canvas n\'a pas encore rendu son étendue', () => {
    // Jamais zéro : une page blanche serait pire qu'une page approximative.
    const root = document.createElement('div')
    Object.defineProperty(root, 'scrollWidth', { value: 800, configurable: true })
    Object.defineProperty(root, 'scrollHeight', { value: 600, configurable: true })

    expect(modelLayoutSurface.getPrintLayout!(root)).toEqual({
      mode: 'plane', width: 800, height: 600,
    })
  })
})

describe('tableSchemaSurface — régime flux, sécable par ligne', () => {
  it('chaque champ est une coupure possible, les en-têtes sont des titres', () => {
    // Une entité de cinquante champs traitée en bloc insécable serait réduite
    // jusqu'à l'illisible pour tenir sur une page.
    const root = document.createElement('div')
    root.innerHTML = `
      <table><thead><tr><th>Nom</th></tr></thead></table>
      <div data-testid="field-row-0"></div>
      <div data-testid="field-row-1"></div>
      <div data-testid="relation-row-0"></div>`
    geometry(new Map())

    const layout = tableSchemaSurface.getPrintLayout!(root)

    expect(layout.mode).toBe('flow')
    const kinds = layout.mode === 'flow' ? layout.blocks.map((b) => b.kind) : []
    expect(kinds.filter((k) => k === 'break')).toHaveLength(3)
    expect(kinds).toContain('heading')
    // Aucun bloc insécable : rien n'oblige à réduire une grille pour l'imprimer.
    expect(kinds).not.toContain('component')
  })
})

describe('surface sans capacité — le repli', () => {
  it('le texte brut ne déclare RIEN : il sera tuilé par la page', () => {
    // Choix délibéré : le repli `plane` dégénère en tranchage vertical pour un
    // contenu qui n'est pas plus large qu'une page. Rien à déclarer, rien à
    // perdre — alors qu'un repli qui tronque ne se voit pas.
    expect(plainTextSurface.getPrintLayout).toBeUndefined()
  })
})

describe('tuilage à l\'impression — la copie par colonne', () => {
  it('une seule colonne : AUCUNE copie émise', () => {
    // Le cas courant. Émettre une copie coûterait un rendu de canevas de plus,
    // pour rien.
    expect(tileColumns(600, 700)).toBe(1)
    expect(tileGrid(600, 1400, 700, 700).every((t) => t.col === 1)).toBe(true)
  })

  it('l\'ordre des pages imprimées est celui des colonnes', () => {
    // C'est la coupure verticale NATURELLE du navigateur qui produit l'ordre :
    // une copie par colonne, chacune coupée en pages de haut en bas, dans
    // l'ordre du flux. Toute la colonne 1, puis toute la colonne 2.
    const grid = tileGrid(1400, 1400, 700, 700)
    expect(grid.map((t) => `${t.col}:${t.row}`)).toEqual(['1:1', '1:2', '2:1', '2:2'])
    expect(tileColumns(1400, 700)).toBe(2)
  })
})
