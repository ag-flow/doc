import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useQuerySpecState } from '../hooks/useQuerySpecState'

describe('useQuerySpecState', () => {
  it('starts in browse mode with an empty spec', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    expect(result.current.mode).toBe('browse')
    expect(result.current.spec).toEqual({
      filters: [],
      sort: [],
      projection: null,
      page: 1,
      page_size: 100,
    })
  })

  it('setting a filter switches to query mode and resets page to 1', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.setPage(3))
    act(() => result.current.setFilter('statut', { op: 'eq', value: 'done' }))
    expect(result.current.mode).toBe('query')
    expect(result.current.spec.filters).toEqual([{ prop: 'statut', op: 'eq', value: 'done' }])
    expect(result.current.spec.page).toBe(1)
  })

  it('setting a filter on the same prop replaces the previous clause', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.setFilter('statut', { op: 'eq', value: 'done' }))
    act(() => result.current.setFilter('statut', { op: 'in', values: ['a', 'b'] }))
    expect(result.current.spec.filters).toEqual([{ prop: 'statut', op: 'in', values: ['a', 'b'] }])
  })

  it('clearing the only active filter reverts to browse mode', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.setFilter('statut', { op: 'eq', value: 'done' }))
    act(() => result.current.setFilter('statut', null))
    expect(result.current.mode).toBe('browse')
    expect(result.current.spec.filters).toEqual([])
  })

  it('toggleSort cycles asc → desc → none on the same key', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.toggleSort('title'))
    expect(result.current.spec.sort).toEqual([{ key: 'title', dir: 'asc' }])
    expect(result.current.mode).toBe('query')

    act(() => result.current.toggleSort('title'))
    expect(result.current.spec.sort).toEqual([{ key: 'title', dir: 'desc' }])

    act(() => result.current.toggleSort('title'))
    expect(result.current.spec.sort).toEqual([])
    expect(result.current.mode).toBe('browse')
  })

  it('toggleSort on a new key replaces the previous single-key sort', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.toggleSort('title'))
    act(() => result.current.toggleSort('created_at'))
    expect(result.current.spec.sort).toEqual([{ key: 'created_at', dir: 'asc' }])
  })

  it('additive toggleSort (Maj-clic) composes a multi-key sort in click order', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.toggleSort('statut'))
    act(() => result.current.toggleSort('title', true))
    expect(result.current.spec.sort).toEqual([
      { key: 'statut', dir: 'asc' },
      { key: 'title', dir: 'asc' },
    ])
  })

  it('additive toggleSort cycles a key in place then drops it, keeping the others', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.toggleSort('statut'))
    act(() => result.current.toggleSort('title', true))
    // asc → desc sur 'statut' sans perdre 'title' (l'ordre est préservé).
    act(() => result.current.toggleSort('statut', true))
    expect(result.current.spec.sort).toEqual([
      { key: 'title', dir: 'asc' },
      { key: 'statut', dir: 'desc' },
    ])
    // desc → retirée : ne reste que 'title'.
    act(() => result.current.toggleSort('statut', true))
    expect(result.current.spec.sort).toEqual([{ key: 'title', dir: 'asc' }])
  })

  it('a non-additive click collapses a multi-key sort back to a single key', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.toggleSort('statut'))
    act(() => result.current.toggleSort('title', true))
    act(() => result.current.toggleSort('title'))
    expect(result.current.spec.sort).toEqual([{ key: 'title', dir: 'desc' }])
  })

  it('setProjection sets the projection and is a no-op when unchanged', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.setProjection(['statut', 'points']))
    expect(result.current.spec.projection).toEqual(['statut', 'points'])
    // Projection ne bascule pas le mode (reste browse tant que pas de filtre/tri).
    expect(result.current.mode).toBe('browse')

    const specBefore = result.current.spec
    // Même contenu (nouvelle référence de tableau) → aucune nouvelle identité de spec.
    act(() => result.current.setProjection(['statut', 'points']))
    expect(result.current.spec).toBe(specBefore)

    act(() => result.current.setProjection(null))
    expect(result.current.spec.projection).toBeNull()
  })

  it('loadSpec hydrates an external QuerySpec (e.g. a saved query) and derives mode', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() =>
      result.current.loadSpec({
        filters: [{ prop: 'priorite', op: 'gt', value: '3' }],
        sort: [],
        projection: ['statut'],
        page: 2,
        page_size: 50,
      }),
    )
    expect(result.current.mode).toBe('query')
    expect(result.current.spec.page).toBe(2)
    expect(result.current.spec.projection).toEqual(['statut'])
  })

  it('reset clears filters/sort/projection and preserves page_size', () => {
    const { result } = renderHook(() => useQuerySpecState(100))
    act(() => result.current.setFilter('statut', { op: 'eq', value: 'done' }))
    act(() => result.current.setPage(4))
    act(() => result.current.reset())
    expect(result.current.mode).toBe('browse')
    expect(result.current.spec).toEqual({
      filters: [],
      sort: [],
      projection: null,
      page: 1,
      page_size: 100,
    })
  })
})
