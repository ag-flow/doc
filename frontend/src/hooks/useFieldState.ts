import { useCallback, useState } from 'react'
import { ApiError, docsApi, type PropertyValueOut, type ValueConflictDetail } from '../lib/api'

export type FieldStatus = 'idle' | 'dirty' | 'saving' | 'conflict' | 'error'

export type ValueType = 'text' | 'int' | 'restricted_list'

export interface FieldServerState {
  version: number
  value: string | null
  allowed_value_slug: string | null
}

export interface FieldState {
  status: FieldStatus
  value: string | null
  baseVersion: number | null
  serverState?: FieldServerState
  errorMessage?: string
}

interface UseFieldStateResult {
  state: FieldState
  setValue: (value: string | null) => void
  save: (ws: string, docId: string, propSlug: string, valueType: ValueType) => Promise<void>
  keepServer: () => void
  keepMine: (ws: string, docId: string, propSlug: string, valueType: ValueType) => Promise<void>
  setEdit: () => void
}

/** Construit le corps PUT selon le type de la propriété. */
function buildBody(
  value: string | null,
  valueType: ValueType,
  expected_version: number | null,
): { value?: string | null; allowed_value_slug?: string | null; expected_version: number | null } {
  if (valueType === 'restricted_list') {
    return { allowed_value_slug: value, expected_version }
  }
  return { value, expected_version }
}

function isConflictDetail(detail: unknown): detail is ValueConflictDetail {
  return (
    typeof detail === 'object' &&
    detail !== null &&
    'version' in detail &&
    typeof (detail as { version: unknown }).version === 'number'
  )
}

/** État local d'un champ de propriété, avec sauvegarde optimiste et conflit 409. */
export function useFieldState(
  initialValue: string | null,
  baseVersion: number | null,
): UseFieldStateResult {
  const [state, setState] = useState<FieldState>({
    status: 'idle',
    value: initialValue,
    baseVersion,
  })

  const setValue = useCallback((value: string | null) => {
    setState((prev) => ({ ...prev, value, status: 'dirty' }))
  }, [])

  const setEdit = useCallback(() => {
    setState((prev) => ({ ...prev, status: 'dirty' }))
  }, [])

  const persist = useCallback(
    async (
      ws: string,
      docId: string,
      propSlug: string,
      valueType: ValueType,
      value: string | null,
      expected_version: number | null,
    ) => {
      setState((prev) => ({ ...prev, status: 'saving' }))
      try {
        const res: PropertyValueOut = await docsApi.putDocumentValue(
          ws,
          docId,
          propSlug,
          buildBody(value, valueType, expected_version),
        )
        setState({ status: 'idle', value, baseVersion: res.version })
      } catch (err) {
        if (err instanceof ApiError && err.status === 409 && isConflictDetail(err.detail)) {
          setState((prev) => ({ ...prev, status: 'conflict', serverState: err.detail as FieldServerState }))
        } else if (err instanceof ApiError && err.status === 422) {
          setState((prev) => ({ ...prev, status: 'error', errorMessage: err.message }))
        } else {
          setState((prev) => ({
            ...prev,
            status: 'error',
            errorMessage: err instanceof Error ? err.message : String(err),
          }))
        }
      }
    },
    [],
  )

  const save = useCallback(
    (ws: string, docId: string, propSlug: string, valueType: ValueType) =>
      persist(ws, docId, propSlug, valueType, state.value, state.baseVersion),
    [persist, state.value, state.baseVersion],
  )

  const keepServer = useCallback(() => {
    setState((prev) =>
      prev.serverState
        ? {
            status: 'idle',
            value: prev.serverState.value ?? prev.serverState.allowed_value_slug,
            baseVersion: prev.serverState.version,
          }
        : { ...prev, status: 'idle' },
    )
  }, [])

  const keepMine = useCallback(
    async (ws: string, docId: string, propSlug: string, valueType: ValueType) => {
      const serverVersion = state.serverState?.version ?? state.baseVersion
      await persist(ws, docId, propSlug, valueType, state.value, serverVersion)
    },
    [persist, state.serverState, state.baseVersion, state.value],
  )

  return { state, setValue, save, keepServer, keepMine, setEdit }
}
