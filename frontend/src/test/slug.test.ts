import { describe, it, expect } from 'vitest'
import { labelToSlug } from '../lib/slug'

describe('labelToSlug', () => {
  it('lowercases', () => expect(labelToSlug('Hello')).toBe('hello'))
  it('replaces spaces with dashes', () => expect(labelToSlug('Mon Type')).toBe('mon-type'))
  it('replaces digits and spaces with dashes, then trims', () => expect(labelToSlug('Type 1')).toBe('type'))
  it('collapses consecutive dashes and trims', () => expect(labelToSlug('Type  1')).toBe('type'))
  it('trims leading and trailing dashes', () => expect(labelToSlug('  hello  ')).toBe('hello'))
  it('replaces special chars and trims leading dash', () => expect(labelToSlug('Épic & Feature!')).toBe('pic-feature'))
  it('handles already valid slug', () => expect(labelToSlug('mon-type')).toBe('mon-type'))
  it('returns empty string for all special chars', () => expect(labelToSlug('123')).toBe(''))
})
