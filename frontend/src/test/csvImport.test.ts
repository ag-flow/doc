import { describe, it, expect } from 'vitest'
import { inferColumnType, slugifyHeader, parseCsv } from '../lib/csvImport'

describe('inferColumnType', () => {
  it('infers int for whole numbers', () => {
    expect(inferColumnType(['1', '2', '-3'])).toBe('int')
  })
  it('infers float when a decimal is present', () => {
    expect(inferColumnType(['1', '2.5', '3'])).toBe('float')
  })
  it('infers date for ISO dates', () => {
    expect(inferColumnType(['2020-01-01', '2021-12-31'])).toBe('date')
  })
  it('infers bool for boolean-like values', () => {
    expect(inferColumnType(['true', 'false', 'oui', 'non'])).toBe('bool')
  })
  it('infers url for http(s) urls', () => {
    expect(inferColumnType(['https://a.com', 'http://b.org'])).toBe('url')
  })
  it('falls back to text on mixed values', () => {
    expect(inferColumnType(['1', 'hello'])).toBe('text')
  })
  it('ignores empty values and defaults to text when all empty', () => {
    expect(inferColumnType(['', '  ', ''])).toBe('text')
  })
})

describe('slugifyHeader', () => {
  it('lowercases and replaces invalid chars', () => {
    expect(slugifyHeader('Nom Complet !')).toBe('nom-complet')
  })
  it('falls back to "col" on empty', () => {
    expect(slugifyHeader('   ')).toBe('col')
  })
})

describe('parseCsv', () => {
  it('parses headers, infers types and returns rows', () => {
    const { columns, rows } = parseCsv('name,age\nAlice,30\nBob,25')
    expect(columns.map((c) => c.slug)).toEqual(['name', 'age'])
    expect(columns.map((c) => c.type)).toEqual(['text', 'int'])
    expect(rows).toEqual([
      ['Alice', '30'],
      ['Bob', '25'],
    ])
  })

  it('dedups duplicate header slugs', () => {
    const { columns } = parseCsv('name,name\na,b')
    expect(columns.map((c) => c.slug)).toEqual(['name', 'name-2'])
  })

  it('synthesizes column names when hasHeader is false', () => {
    const { columns, rows } = parseCsv('a,1\nb,2', false)
    expect(columns.map((c) => c.slug)).toEqual(['col-1', 'col-2'])
    expect(rows.length).toBe(2)
  })

  it('returns empty result on blank input', () => {
    expect(parseCsv('')).toEqual({ columns: [], rows: [] })
  })
})
