import { describe, it, expect } from 'vitest'
import { labelToSlug } from '../lib/slug'

describe('labelToSlug', () => {
  it('lowercases', () => expect(labelToSlug('Hello')).toBe('hello'))
  it('replaces spaces with dashes', () => expect(labelToSlug('Mon Type')).toBe('mon-type'))
  it('keeps digits (FE-12)', () => expect(labelToSlug('Type 1')).toBe('type-1'))
  it('collapses consecutive dashes', () => expect(labelToSlug('Type  1')).toBe('type-1'))
  it('trims leading and trailing dashes', () => expect(labelToSlug('  hello  ')).toBe('hello'))
  it('replaces special chars and trims leading dash', () => expect(labelToSlug('Épic & Feature!')).toBe('pic-feature'))
  it('handles already valid slug', () => expect(labelToSlug('mon-type')).toBe('mon-type'))
  it('keeps a digits-only label (FE-12)', () => expect(labelToSlug('123')).toBe('123'))
})
