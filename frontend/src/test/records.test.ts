import { describe, it, expect } from 'vitest'
import { parseAttrs, parseRecords, serializeAttrs, serializeRecords } from '../lib/blockCodecs/records'

describe('parseAttrs', () => {
  it('parse clé="valeur" avec échappement \\"', () => {
    const { attrs, unknown } = parseAttrs(' title="Plan \\"urgent\\"" label="Étape"')
    expect(attrs.title).toBe('Plan "urgent"')
    expect(attrs.label).toBe('Étape')
    expect(unknown).toEqual([])
  })

  it('signale les fragments mal formés', () => {
    const { attrs, unknown } = parseAttrs(' title="ok" broken=noquotes')
    expect(attrs.title).toBe('ok')
    expect(unknown.length).toBeGreaterThan(0)
  })

  it('round-trip serializeAttrs → parseAttrs', () => {
    const src = { title: 'Avec "guillemets" et \\ backslash', type: 'pie' }
    const { attrs } = parseAttrs(serializeAttrs(src))
    expect(attrs).toEqual(src)
  })
})

describe('parseRecords', () => {
  it('une ligne = un enregistrement, espaces trimés, lignes vides ignorées', () => {
    const r = parseRecords('  a | b \n\n c|d ')
    expect(r.rows).toEqual([['a', 'b'], ['c', 'd']])
  })

  it('échappement \\| pour un pipe littéral', () => {
    const r = parseRecords('a \\| b | c')
    expect(r.rows).toEqual([['a | b', 'c']])
  })

  it('en-tête EXPLICITE (jamais devinée)', () => {
    const with_ = parseRecords('H1 | H2\na | b', { header: true })
    expect(with_.header).toEqual(['H1', 'H2'])
    expect(with_.rows).toEqual([['a', 'b']])
    const without = parseRecords('H1 | H2\na | b')
    expect(without.header).toBeNull()
    expect(without.rows.length).toBe(2)
  })

  it('champs manquants complétés, champs en excès ignorés AVEC diagnostic', () => {
    const r = parseRecords('seul\na | b | c | d', { fields: 2 })
    expect(r.rows).toEqual([['seul', ''], ['a', 'b']])
    expect(r.diagnostics.length).toBe(1)
    expect(r.diagnostics[0].kind).toBe('extra_fields')
  })

  it('round-trip serializeRecords → parseRecords (pipe ré-échappé)', () => {
    const rows = [['a | b', 'c']]
    const r = parseRecords(serializeRecords(rows))
    expect(r.rows).toEqual(rows)
  })
})
