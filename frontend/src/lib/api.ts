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

async function requestText(path: string, options: RequestInit = {}): Promise<string> {
  const token = getToken()
  const headers: Record<string, string> = {
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
  return res.text()
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
  delete: <T = void>(path: string) => request<T>(path, { method: 'DELETE' }),
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
  exposed: boolean
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
  exposed: boolean
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

/** Valeur brute d'une propriété pour un doc, telle que retournée par le batch /values. */
export interface DocPropValue {
  prop_slug: string
  prop_type: string
  value: string | null
  allowed_value_slug: string | null
  allowed_value_label: string | null
  allowed_value_color: string | null
}

/** Allowed value enrichie (endpoint /types/rich). */
export interface AllowedValueRich {
  slug: string
  label: string
  position: number
  color: string | null
}

/** Définition de propriété enrichie (endpoint /types/rich). */
export interface PropertyDefRich {
  slug: string
  label: string
  type: 'text' | 'int' | 'restricted_list'
  default_value: string | null
  required: boolean
  allowed_values: AllowedValueRich[]
}

/** Type fonctionnel enrichi de ses propriétés + allowed_values (endpoint /types/rich). */
export interface FunctionalTypeRich extends FunctionalType {
  properties: PropertyDefRich[]
}

// ── Endpoints documents / blocks ────────────────────────────────────────────

export const docsApi = {
  getBlocks: (ws: string) => api.get<DataBlockOut[]>(`/workspaces/${ws}/blocks`),

  getTypesRich: (ws: string) =>
    api.get<FunctionalTypeRich[]>(`/workspaces/${ws}/types/rich`),

  getBlockDocuments: (ws: string, block: string) =>
    api.get<DocumentOut[]>(`/workspaces/${ws}/blocks/${block}/documents`),

  getBlockValues: (ws: string, block: string) =>
    api.get<Record<string, DocPropValue[]>>(`/workspaces/${ws}/blocks/${block}/values`),

  getAllowedTypes: (ws: string, block: string, parentId?: string) => {
    const qs = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ''
    return api.get<AllowedTypeOut[]>(`/workspaces/${ws}/blocks/${block}/allowed-types${qs}`)
  },

  createDocument: (
    ws: string,
    block: string,
    body: { title: string; functional_type_slug: string; parent_id?: string },
  ) => api.post<DocumentOut>(`/workspaces/${ws}/blocks/${block}/documents`, body),

  listDocuments: (ws: string) =>
    api.get<DocumentOut[]>(`/workspaces/${ws}/documents`),

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

  deleteDocument: (ws: string, docId: string) =>
    api.delete(`/workspaces/${ws}/documents/${docId}`),

  setDocumentExposed: (ws: string, docId: string, exposed: boolean) =>
    api.patch<DocumentOut>(`/workspaces/${ws}/documents/${docId}/exposed`, { exposed }),

  setBlockExposed: (ws: string, blockSlug: string, exposed: boolean) =>
    api.patch<DataBlockOut>(`/workspaces/${ws}/blocks/${blockSlug}/exposed`, { exposed }),
}

// ── API publique (sans authentification) ────────────────────────────────────

async function pubGet<T>(path: string): Promise<T> {
  const res = await fetch(`/pub${path}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new ApiError(res.status, detail, `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const publicApi = {
  getDocument: (docId: string) => pubGet<DocumentOut>(`/documents/${docId}`),
  getChildren: (docId: string) => pubGet<DocumentOut[]>(`/documents/${docId}/children`),
}

export const templatesApi = {
  getYaml: (slug: string) => requestText(`/templates/${slug}/yaml`),
  saveYaml: (slug: string, content: string) =>
    api.put<TemplateInfo>(`/templates/${slug}/yaml`, { yaml_content: content }),
  delete: (slug: string) => api.delete(`/templates/${slug}`),
}

// ── Types réactions / commentaires ───────────────────────────────────────────

export interface ReactionOut {
  likes: number
  dislikes: number
  my_reaction: 1 | -1 | null
  last_likes: string[]
  last_dislikes: string[]
}

export interface CommentOut {
  id: string
  author_label: string
  body: string
  is_mine: boolean
  reactions: ReactionOut
  created_at: string
  updated_at: string
}

// ── API réactions / commentaires ─────────────────────────────────────────────

export const reactionsApi = {
  getDocReactions: (ws: string, docId: string) =>
    api.get<ReactionOut>(`/workspaces/${ws}/documents/${docId}/reactions`),

  toggleDocReaction: (ws: string, docId: string, nature: 1 | -1) =>
    api.put<ReactionOut>(`/workspaces/${ws}/documents/${docId}/reaction`, { nature }),

  removeDocReaction: (ws: string, docId: string) =>
    api.delete<ReactionOut>(`/workspaces/${ws}/documents/${docId}/reaction`),

  getComments: (ws: string, docId: string) =>
    api.get<CommentOut[]>(`/workspaces/${ws}/documents/${docId}/comments`),

  addComment: (ws: string, docId: string, body: string) =>
    api.post<CommentOut>(`/workspaces/${ws}/documents/${docId}/comments`, { body }),

  deleteComment: (ws: string, docId: string, commentId: string) =>
    api.delete<void>(`/workspaces/${ws}/documents/${docId}/comments/${commentId}`),

  toggleCommentReaction: (ws: string, docId: string, commentId: string, nature: 1 | -1) =>
    api.put<ReactionOut>(
      `/workspaces/${ws}/documents/${docId}/comments/${commentId}/reaction`,
      { nature }
    ),

  removeCommentReaction: (ws: string, docId: string, commentId: string) =>
    api.delete<ReactionOut>(
      `/workspaces/${ws}/documents/${docId}/comments/${commentId}/reaction`
    ),
}

// ── Types référencement ──────────────────────────────────────────────────────

export interface DocumentSearchResult {
  id: string
  title: string
  type: string | null
  bloc: string | null
}

export interface BrokenLinkBloc {
  bloc: string | null
  docs_with_broken_links: number
}

export interface BrokenLinkDetail {
  source_ref: string
  source_title: string
  target_ref: string | null
  target_label: string
}

export const referencesApi = {
  searchDocuments: (ws: string, q: string, limit = 10) =>
    api.get<DocumentSearchResult[]>(
      `/workspaces/${ws}/documents/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),

  getBrokenLinks: (ws: string) =>
    api.get<BrokenLinkBloc[]>(`/workspaces/${ws}/broken-links`),

  getBrokenLinksDetail: (ws: string, blocId: string) =>
    api.get<BrokenLinkDetail[]>(`/workspaces/${ws}/blocs/${blocId}/broken-links`),
}

// ── Webhooks ────────────────────────────────────────────────────────────────

export interface WebhookOut {
  id: string
  workspace_technical_key: string
  label: string
  url: string
  headers: Record<string, string>
  events: string[]
  active: boolean
  created_at: string
  updated_at: string
}

export interface WebhookTestOut {
  status_code: number | null
  error: string | null
}

export const ALL_EVENTS = ['document.created', 'document.updated', 'document.deleted'] as const
export type WebhookEvent = (typeof ALL_EVENTS)[number]

// ── Auth / me ───────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string
  email: string
  label: string
  is_superadmin: boolean
  disabled: boolean
}

/** Décode le payload JWT localement (sans vérification — le serveur valide). */
export function isSuperAdmin(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return Boolean(payload.is_superadmin)
  } catch {
    return false
  }
}

// ── Vault wallets ───────────────────────────────────────────────────────────

export interface VaultWalletOut {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export interface VaultSecretOut {
  id: string
  slug: string
  label: string
  created_at: string
  updated_at: string
}

export const vaultApi = {
  listWallets: () => api.get<VaultWalletOut[]>('/admin/vault/wallets'),
  createWallet: (body: { name: string; api_key: string }) =>
    api.post<VaultWalletOut>('/admin/vault/wallets', body),
  deleteWallet: (id: string) => api.delete(`/admin/vault/wallets/${id}`),
}

export const secretsApi = {
  list: () => api.get<VaultSecretOut[]>('/admin/secrets'),
  create: (body: { label: string; slug: string; value: string }) =>
    api.post<VaultSecretOut>('/admin/secrets', body),
  delete: (id: string) => api.delete(`/admin/secrets/${id}`),
}

// ── OIDC admin ──────────────────────────────────────────────────────────────

export interface OidcConfigOut {
  id: string
  issuer: string
  client_id: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export const oidcApi = {
  get: () => api.get<OidcConfigOut | null>('/admin/oidc'),
  set: (body: {
    issuer: string
    client_id: string
    client_secret_ref: string
    enabled: boolean
  }) => api.put<OidcConfigOut>('/admin/oidc', body),
}

// ── Webhooks ────────────────────────────────────────────────────────────────

export const webhooksApi = {
  list: (ws: string) => api.get<WebhookOut[]>(`/workspaces/${ws}/webhooks`),
  get: (ws: string, id: string) => api.get<WebhookOut>(`/workspaces/${ws}/webhooks/${id}`),
  create: (
    ws: string,
    body: {
      label: string
      url: string
      headers: Record<string, string>
      events: string[]
      active: boolean
    },
  ) => api.post<WebhookOut>(`/workspaces/${ws}/webhooks`, body),
  update: (
    ws: string,
    id: string,
    body: Partial<{
      label: string
      url: string
      headers: Record<string, string>
      events: string[]
      active: boolean
    }>,
  ) => api.patch<WebhookOut>(`/workspaces/${ws}/webhooks/${id}`, body),
  delete: (ws: string, id: string) => api.delete(`/workspaces/${ws}/webhooks/${id}`),
  test: (ws: string, id: string) =>
    api.post<WebhookTestOut>(`/workspaces/${ws}/webhooks/${id}/test`, {}),
}

// ── Contrats OpenAPI ────────────────────────────────────────────────────────

export interface ContractOut {
  id: string
  label: string
  source_url: string | null
  version: string | null
  imported_at: string
  updated_at: string
}

export interface OperationOut {
  operation_id: string | null
  method: string
  path: string
  summary: string | null
  parameters: object[]
  request_body: object | null
  body_skeleton: Record<string, unknown> | null
}

export interface ContractDetailOut {
  contract: ContractOut
  operations: OperationOut[]
}

export const contractsApi = {
  list: () => api.get<ContractOut[]>('/admin/contracts'),
  import: (body: { label: string; source_url?: string; raw_spec: object }) =>
    api.post<ContractOut>('/admin/contracts', body),
  detail: (id: string) => api.get<ContractDetailOut>(`/admin/contracts/${id}`),
  refresh: (id: string) => api.post<ContractOut>(`/admin/contracts/${id}/refresh`, {}),
  delete: (id: string) => api.delete(`/admin/contracts/${id}`),
}

// ── Automates ───────────────────────────────────────────────────────────────

export interface AutomationHeaderIn {
  name: string
  value?: string | null
  secret_ref?: string | null
  required?: boolean
  enabled?: boolean
}

export interface AutomationHeaderOut {
  id: string
  name: string
  value: string | null
  secret_ref: string | null
  required: boolean
  enabled: boolean
}

export interface AutomationOut {
  id: string
  workspace_technical_key: string
  label: string
  active: boolean
  on_create: boolean
  on_update: boolean
  delay_minutes: number
  contract_ref: string | null
  operation_id: string | null
  url: string
  http_method: string
  body_template: string | null
  headers: AutomationHeaderOut[]
  created_at: string
  updated_at: string
}

export interface AutomationCreate {
  label: string
  active?: boolean
  on_create?: boolean
  on_update?: boolean
  delay_minutes?: number
  contract_ref?: string | null
  operation_id?: string | null
  url: string
  http_method: string
  body_template?: string | null
  headers?: AutomationHeaderIn[]
}

export interface AutomationRunOut {
  id: string
  automation_ref: string
  document_ref: string
  document_version: number
  change_log_seq: number
  status: string
  executed_at: string
}

export const automationsApi = {
  list: (ws: string) => api.get<AutomationOut[]>(`/workspaces/${ws}/automations`),
  create: (ws: string, body: AutomationCreate) =>
    api.post<AutomationOut>(`/workspaces/${ws}/automations`, body),
  get: (ws: string, id: string) => api.get<AutomationOut>(`/workspaces/${ws}/automations/${id}`),
  update: (ws: string, id: string, body: Partial<AutomationCreate>) =>
    api.patch<AutomationOut>(`/workspaces/${ws}/automations/${id}`, body),
  delete: (ws: string, id: string) => api.delete(`/workspaces/${ws}/automations/${id}`),
  listRuns: (ws: string, id: string, limit = 50) =>
    api.get<AutomationRunOut[]>(`/workspaces/${ws}/automations/${id}/runs?limit=${limit}`),
  replay: (ws: string, id: string, runId: string) =>
    api.post<AutomationRunOut>(`/workspaces/${ws}/automations/${id}/runs/${runId}/replay`, {}),
}
