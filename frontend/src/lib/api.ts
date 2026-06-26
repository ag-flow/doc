const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '') + '/api'

const TOKEN_KEY = 'docflow_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** Erreur HTTP enrichie : porte le code statut et le corps `detail` brut. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const m = (detail as { message?: unknown }).message
    if (typeof m === 'string') return m
  }
  return fallback
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new ApiError(401, null, 'Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body as { detail?: unknown }).detail ?? null
    throw new ApiError(res.status, detail, detailMessage(detail, res.statusText))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  get: <T>(path: string) => request<T>(path),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: 'DELETE' }),
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface FunctionalType {
  id: string
  slug: string
  label: string
  parent_slug: string | null
  workspace_slug: string
  created_at: string
  updated_at: string
}

export interface AllowedValueOut {
  slug: string
  label: string
  color: string | null
  position: number
}

/** Définition de propriété telle qu'exposée par GET /workspaces/{ws}/types. */
export interface PropertyDef {
  slug: string
  label: string
  type: 'text' | 'int' | 'restricted_list'
  required: boolean
  allowed_values?: AllowedValueOut[]
}

/** Type fonctionnel enrichi de ses définitions de propriété (selon backend). */
export interface FunctionalTypeWithProps extends FunctionalType {
  properties?: PropertyDef[]
}

export interface WorkspaceOut {
  workspace_technical_key: string
  slug: string
  label: string
  description: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface TemplateInfo {
  template: string
  label: string
  version: number
  path: string
  concrete_types: number
  type_slugs: string[]
}

export interface DocumentOut {
  doc_technical_key: string
  title: string
  type: string
  content: string | null
  version: number
  parent_id: string | null
  functional_type_slug: string | null
  workspace_slug: string
  data_block_ref: string
  created_at: string
  updated_at: string
}

export interface DataBlockOut {
  id: string
  slug: string
  label: string
  functional_type_slug: string
  parent_slug: string | null
  workspace_slug: string
  created_at: string
  updated_at: string
}

export interface PropertyValueOut {
  prop_slug: string
  prop_label: string
  type: 'text' | 'int' | 'restricted_list'
  version: number | null
  value: string | null
  allowed_value_slug: string | null
  allowed_value_label: string | null
  required: boolean
}

/** Corps renvoyé dans `detail` d'un 409 sur PUT value. */
export interface ValueConflictDetail {
  version: number
  value: string | null
  allowed_value_slug: string | null
}

export interface AllowedTypeOut {
  slug: string
  label: string
}

// ── Endpoints documents / blocks ────────────────────────────────────────────

export const docsApi = {
  getBlocks: (ws: string) => api.get<DataBlockOut[]>(`/workspaces/${ws}/blocks`),

  getBlockDocuments: (ws: string, block: string) =>
    api.get<DocumentOut[]>(`/workspaces/${ws}/blocks/${block}/documents`),

  getAllowedTypes: (ws: string, block: string, parentId?: string) => {
    const qs = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ''
    return api.get<AllowedTypeOut[]>(`/workspaces/${ws}/blocks/${block}/allowed-types${qs}`)
  },

  createDocument: (
    ws: string,
    block: string,
    body: { title: string; functional_type_slug: string; parent_id?: string },
  ) => api.post<DocumentOut>(`/workspaces/${ws}/blocks/${block}/documents`, body),

  getDocument: (ws: string, docId: string) =>
    api.get<DocumentOut>(`/workspaces/${ws}/documents/${docId}`),

  patchDocument: (
    ws: string,
    docId: string,
    body: { title?: string; content?: string; expected_version: number },
  ) => api.patch<DocumentOut>(`/workspaces/${ws}/documents/${docId}`, body),

  getDocumentValues: (ws: string, docId: string) =>
    api.get<PropertyValueOut[]>(`/workspaces/${ws}/documents/${docId}/values`),

  putDocumentValue: (
    ws: string,
    docId: string,
    propSlug: string,
    body: {
      value?: string | null
      allowed_value_slug?: string | null
      expected_version: number | null
    },
  ) => api.put<PropertyValueOut>(`/workspaces/${ws}/documents/${docId}/values/${propSlug}`, body),
}
