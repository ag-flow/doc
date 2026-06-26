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
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? res.statusText)
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
  created_at: string
  updated_at: string
}
