import { describe, it, expect } from 'vitest'
import { relativeDate } from '../lib/relativeDate'

const NOW = new Date('2026-07-27T12:00:00Z')

describe('relativeDate', () => {
  it('granularité courte puis date absolue au-delà d’une semaine', () => {
    expect(relativeDate('2026-07-27T11:59:30Z', NOW)).toBe("à l'instant")
    expect(relativeDate('2026-07-27T11:40:00Z', NOW)).toBe('il y a 20 min')
    expect(relativeDate('2026-07-27T09:00:00Z', NOW)).toBe('il y a 3 h')
    expect(relativeDate('2026-07-26T10:00:00Z', NOW)).toBe('hier')
    expect(relativeDate('2026-07-24T10:00:00Z', NOW)).toBe('il y a 3 j')
    expect(relativeDate('2026-06-01T10:00:00Z', NOW)).toMatch(/juin 2026/)
  })

  it('date invalide → chaîne vide (jamais « Invalid Date » à l’écran)', () => {
    expect(relativeDate('pas-une-date', NOW)).toBe('')
  })
})
