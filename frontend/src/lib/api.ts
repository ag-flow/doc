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

/** Endpoints d'authentification : un 401 y est un échec de login légitime, pas une
 *  session expirée. On ne doit ni purger de token ni recharger la page. */
const AUTH_PATHS = ['/auth/login', '/auth/methods', '/auth/oidc', '/setup/init-admin']

function isAuthPath(path: string): boolean {
  return AUTH_PATHS.some((p) => path.startsWith(p))
}

/** Gère un 401 de façon centralisée. On ne purge le token et ne redirige vers /login
 *  que pour une session réellement expirée : un token était présent ET la requête ne
 *  vise pas un endpoint d'auth. Sinon (login sans token, mauvais mot de passe…) on
 *  laisse l'ApiError remonter pour que l'appelant affiche le message d'erreur au lieu
 *  de recharger brutalement la page. Retourne toujours (throw). */
function handleUnauthorized(path: string, hadToken: boolean): never {
  if (hadToken && !isAuthPath(path)) {
    clearToken()
    window.location.href = '/login'
  }
  throw new ApiError(401, null, 'Unauthorized')
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // Corps d'erreur de validation FastAPI/Pydantic : liste de {msg, loc, type}.
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? (d as { msg?: unknown }).msg : null))
      .filter((m): m is string => typeof m === 'string')
      .map((m) => m.replace(/^Value error, /, ''))
    if (msgs.length > 0) return msgs.join(' ; ')
  }
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
  if (res.status === 401) handleUnauthorized(path, Boolean(token))
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body as { detail?: unknown }).detail ?? null
    throw new ApiError(res.status, detail, detailMessage(detail, res.statusText))
  }
  return res.text()
}

/** Requête retournant un Blob (téléchargement de fichier), avec la même gestion 401 / erreurs que `request`. */
async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (res.status === 401) handleUnauthorized(path, Boolean(token))
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body as { detail?: unknown }).detail ?? null
    throw new ApiError(res.status, detail, detailMessage(detail, res.statusText))
  }
  return res.blob()
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (res.status === 401) handleUnauthorized(path, Boolean(token))
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body as { detail?: unknown }).detail ?? null
    throw new ApiError(res.status, detail, detailMessage(detail, res.statusText))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Requête multipart (upload de fichier) : pas de Content-Type manuel, le
 *  navigateur pose lui-même la boundary du FormData. */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: form, headers })
  if (res.status === 401) handleUnauthorized(path, Boolean(token))
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = (body as { detail?: unknown }).detail ?? null
    throw new ApiError(res.status, detail, detailMessage(detail, res.statusText))
  }
  return res.json() as Promise<T>
}

/** URL absolue d'un chemin API — pour les consommateurs hors `request`
 *  (flux SSE fetch-streaming, qui gèrent eux-mêmes la lecture du corps). */
export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`
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
  getBlob: (path: string) => requestBlob(path),
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface FunctionalType {
  id: string
  slug: string
  label: string
  parent_slug: string | null
  workspace_slug: string
  content_template: string | null
  /** Slug du template ayant créé le type via import ; null = créé à la main. */
  source_template: string | null
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
  type: 'text' | 'int' | 'restricted_list' | 'date' | 'bool' | 'url' | 'float' | 'reference'
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
  /** Renseignés par l'index (`GET /workspaces`) ; 0/null sur une lecture unitaire. */
  blocks_count: number
  documents_count: number
  last_activity_at: string | null
}

export interface TemplateInfo {
  template: string
  label: string
  version: number
  path: string
  concrete_types: number
  type_slugs: string[]
  /** Blocs utilisateurs (tous workspaces) portés par les types de ce template. */
  blocks_count: number
}

export interface GalleryPullDiff {
  template: string
  installed_version: number | null
  remote_version: number
  new_types: string[]
  /** Propriétés ajoutées aux types déjà installés : « type.prop ». */
  new_properties: string[]
}

export interface RemoteTemplateInfo {
  template: string
  label: string
  version: number
  type_slugs: string[]
  concrete_types: number
  installed: boolean
  update_available: boolean
}

export interface GalleryConfig {
  default_url: string | null
}

export interface GallerySourceOut {
  id: string | null
  label: string
  url: string
  builtin: boolean
}

export interface DocumentVersionInfo {
  version_number: number
  title: string
  content_length: number
  created_at: string
}

export interface DocumentVersionOut {
  version_number: number
  title: string
  content: string | null
  created_at: string
}

export interface DocumentOut {
  doc_technical_key: string
  title: string
  type: string
  slug: string | null
  content: string | null
  version: number
  parent_id: string | null
  functional_type_slug: string | null
  workspace_slug: string
  data_block_ref: string
  exposed: boolean
  created_at: string
  updated_at: string
  /** Auteur de la dernière écriture ; null = inconnu. */
  updated_by: string | null
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
  /** Renseignés par le listing (`GET /blocks`) ; 0/null sur une lecture unitaire. */
  documents_count: number
  last_write_at: string | null
}

export interface PropertyValueOut {
  prop_slug: string
  prop_label: string
  type: 'text' | 'int' | 'restricted_list' | 'date' | 'bool' | 'url' | 'float' | 'reference'
  version: number | null
  value: string | null
  allowed_value_slug: string | null
  allowed_value_label: string | null
  required: boolean
  /** 'auto_now' | 'auto_now_create' : propriété gérée par le serveur (lecture seule). */
  behavior: string | null
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
  type: 'text' | 'int' | 'restricted_list' | 'date' | 'bool' | 'url' | 'float' | 'reference'
  default_value: string | null
  required: boolean
  behavior: string | null
  allowed_values: AllowedValueRich[]
}

/** Type fonctionnel enrichi de ses propriétés + allowed_values (endpoint /types/rich). */
export interface FunctionalTypeRich extends FunctionalType {
  properties: PropertyDefRich[]
  /** Nombre de documents portant ce type (renseigné par /types/rich). */
  documents_count: number
}

// ── Moteur de requête (QuerySpec) ───────────────────────────────────────────

/** Opérateurs de filtre — miroir de `Operator` (backend `schemas/query.py`). */
export type QueryOperator =
  | 'eq'
  | 'contains'
  | 'starts_with'
  | 'lt'
  | 'gt'
  | 'between'
  | 'in'
  | 'before'
  | 'after'

export interface FilterClause {
  prop: string
  op: QueryOperator
  /** Valeur unique — tous les opérateurs sauf 'in' et 'between'. */
  value?: string | null
  /** Valeurs multiples — 'in' (liste) ou 'between' (exactement [min, max]). */
  values?: string[] | null
}

export interface SortKey {
  /** slug de propriété | 'title' | 'created_at'. */
  key: string
  dir: 'asc' | 'desc'
}

/** Corps REST de POST .../blocks/{block}/query — miroir de `BlockQueryBody`
 *  (backend `schemas/query.py`). Structure partagée : rejouable telle quelle
 *  par une requête nommée (milestone ultérieur). */
export interface ViewOut {
  id: string
  slug: string
  label: string
  layout: string
  filter: FilterClause[]
  sort: SortKey[]
  group_by: string | null
  columns: string[]
  bloc_ref: string | null
  owner_ref: string | null
  created_at: string
  updated_at: string
}

export interface ViewCreateBody {
  slug: string
  label: string
  layout: string
  filter?: FilterClause[]
  sort?: SortKey[]
  columns?: string[]
  bloc_ref?: string | null
  shared?: boolean
}

/** Préférences d'interface par utilisateur (suivent le compte, pas le navigateur). */
export const prefsApi = {
  get: <T>(key: string) =>
    api.get<{ key: string; value: T | null }>(`/me/preferences/${encodeURIComponent(key)}`),
  set: <T>(key: string, value: T | null) =>
    api.put<{ key: string; value: T | null }>(`/me/preferences/${encodeURIComponent(key)}`, { value }),
}

/** Vues enregistrées : un jeu tri + filtres + colonnes, rappelable. */
export const viewsApi = {
  list: (ws: string) => api.get<ViewOut[]>(`/workspaces/${ws}/views`),
  create: (ws: string, body: ViewCreateBody) =>
    api.post<ViewOut>(`/workspaces/${ws}/views`, body),
  remove: (ws: string, slug: string) => api.delete<void>(`/workspaces/${ws}/views/${slug}`),
}

export interface BlockQueryBody {
  type_slugs?: string[] | null
  filters: FilterClause[]
  sort: SortKey[]
  projection?: string[] | null
  page: number
  page_size: number
}

/** Valeur d'une propriété d'un objet de requête (forme aplatie, sans couleur —
 *  résoudre la couleur depuis les `allowed_values` du type si besoin). */
export interface PropertyValueBrief {
  prop_slug: string
  type: string
  value: string | null
  allowed_value_slug: string | null
  allowed_value_label: string | null
}

export interface BlockObjectOut {
  id: string
  title: string
  functional_type_slug: string | null
  properties: PropertyValueBrief[]
  updated_at: string | null
  updated_by: string | null
}

export interface BlockObjectsPage {
  block_slug: string
  page: number
  page_size: number
  total: number
  has_next: boolean
  objects: BlockObjectOut[]
}

/** Nœud de l'arbre `list_block_tree` : le document + ses valeurs + ses enfants directs. */
export interface BlockTreeNode {
  id: string
  title: string
  functional_type_slug: string | null
  parent_id: string | null
  properties: PropertyValueBrief[]
  children: BlockTreeNode[]
  updated_at: string | null
  updated_by: string | null
}

/** Page de racines d'un bloc (mode browse) : `total`/`has_next` comptent les
 *  racines uniquement — les enfants d'une racine incluse ne consomment pas le `page_size`. */
export interface BlockTreePage {
  block_slug: string
  page: number
  page_size: number
  total: number
  has_next: boolean
  roots: BlockTreeNode[]
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

  /** Mode requête (filtre/tri actif) : liste plate paginée serveur, ≤100/page. */
  queryBlockDocuments: (ws: string, block: string, body: BlockQueryBody) =>
    api.post<BlockObjectsPage>(`/workspaces/${ws}/blocks/${block}/query`, body),

  /** Mode browse : racines paginées (≤100/page) + sous-arbres + valeurs. */
  getBlockTree: (ws: string, block: string, page: number, pageSize: number) =>
    api.get<BlockTreePage>(
      `/workspaces/${ws}/blocks/${block}/tree?page=${page}&page_size=${pageSize}`,
    ),

  createDocument: (
    ws: string,
    block: string,
    body: {
      title: string
      functional_type_slug: string
      parent_id?: string
      slug?: string
      /** Valeurs initiales : requises pour les propriétés required sans défaut. */
      properties?: Record<string, string>
    },
  ) => api.post<DocumentOut>(`/workspaces/${ws}/blocks/${block}/documents`, body),

  listDocuments: (ws: string) =>
    api.get<DocumentOut[]>(`/workspaces/${ws}/documents`),

  getDocument: (ws: string, docId: string) =>
    api.get<DocumentOut>(`/workspaces/${ws}/documents/${docId}`),

  patchDocument: (
    ws: string,
    docId: string,
    body: {
      title?: string; content?: string; expected_version?: number; slug?: string
      /** null = déplacer à la racine du bloc. */
      parent_id?: string | null
      /** Conversion de type à la volée lors d'un déplacement. */
      functional_type_slug?: string
    },
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

  /** Historique des versions (métadonnées, la plus récente d'abord). */
  listVersions: (ws: string, docId: string) =>
    api.get<DocumentVersionInfo[]>(`/workspaces/${ws}/documents/${docId}/versions`),
  getVersion: (ws: string, docId: string, n: number) =>
    api.get<DocumentVersionOut>(`/workspaces/${ws}/documents/${docId}/versions/${n}`),

  setDocumentExposed: (ws: string, docId: string, exposed: boolean) =>
    api.patch<DocumentOut>(`/workspaces/${ws}/documents/${docId}/exposed`, { exposed }),

  setBlockExposed: (ws: string, blockSlug: string, exposed: boolean) =>
    api.patch<DataBlockOut>(`/workspaces/${ws}/blocks/${blockSlug}/exposed`, { exposed }),

  /** Renommage / rattachement d'un bloc (label, parent). */
  updateBlock: (ws: string, blockSlug: string, patch: { label?: string; parent_slug?: string | null }) =>
    api.patch<DataBlockOut>(`/workspaces/${ws}/blocks/${blockSlug}`, patch),

  /** Supprime un bloc. Sans `confirm`, l'API refuse (409) si le bloc a des
   *  dépendants — le message d'erreur porte le décompte à afficher avant de
   *  reconfirmer avec `confirm=true` (cascade assumée). */
  deleteBlock: (ws: string, blockSlug: string, confirm = false) =>
    api.delete<void>(
      `/workspaces/${ws}/blocks/${blockSlug}${confirm ? '?confirm=true' : ''}`,
    ),
}

// ── Artefacts (images des documents) ────────────────────────────────────────

export interface ArtifactCreatedOut {
  id: string
  url: string
  deduplicated: boolean
  filename: string
  extension: string
  media_type: string
  size_bytes: number
  sha256: string
  crc32: number
}

export const artifactsApi = {
  upload: (ws: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<ArtifactCreatedOut>(`/workspaces/${ws}/artifacts`, form)
  },
  getBlob: (ws: string, id: string) => requestBlob(`/workspaces/${ws}/artifacts/${id}`),
}

// ── API publique (sans authentification) ────────────────────────────────────

export type ChangeEntityKind = 'document' | 'type' | 'property' | 'block' | 'template'

export interface ChangeEntry {
  seq: number
  nature: string
  entity_kind: ChangeEntityKind
  entity_id: string | null
  document_id: string | null
  occurred_at: string
}

export interface ChangeFeedOut {
  changes: ChangeEntry[]
  next_cursor: number
  has_more: boolean
}

export const changesApi = {
  get: (ws: string, since: number, limit = 200) =>
    api.get<ChangeFeedOut>(`/workspaces/${ws}/changes?since=${since}&limit=${limit}`),
}

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

export const galleryApi = {
  getConfig: () => api.get<GalleryConfig>('/templates/gallery/config'),
  listSources: () => api.get<GallerySourceOut[]>('/templates/gallery/sources'),
  addSource: (label: string, url: string) =>
    api.post<GallerySourceOut>('/templates/gallery/sources', { label, url }),
  deleteSource: (id: string) => api.delete(`/templates/gallery/sources/${id}`),
  list: (source_url: string) =>
    api.get<RemoteTemplateInfo[]>(`/templates/gallery?source_url=${encodeURIComponent(source_url)}`),
  pull: (source_url: string, template_slug: string) =>
    api.post<TemplateInfo>('/templates/gallery/pull', { source_url, template_slug }),
  /** Ce que la mise à jour changerait — avant confirmation, aucune écriture. */
  pullDiff: (source_url: string, template_slug: string) =>
    api.post<GalleryPullDiff>('/templates/gallery/pull/diff', { source_url, template_slug }),
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

export interface BacklinkOut {
  source_id: string
  source_title: string
  source_type: string | null
  bloc: string | null
  target_label: string
}

export interface GlobalSearchResult {
  id: string
  title: string
  type: string | null
  workspace_slug: string
  block_slug: string | null
}

export interface DocLocationOut {
  id: string
  title: string
  workspace_slug: string
  block_slug: string | null
}

export const referencesApi = {
  /** Résout un lien interne docflow://doc/{id} en workspace/bloc. */
  locate: (docId: string) =>
    api.get<DocLocationOut>(`/documents/locate/${docId}`),

  /** Recherche par titre sur tous les workspaces accessibles à l'appelant. */
  searchGlobal: (q: string, limit = 10) =>
    api.get<GlobalSearchResult[]>(
      `/search/documents?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  searchDocuments: (ws: string, q: string, limit = 10, type?: string) =>
    api.get<DocumentSearchResult[]>(
      `/workspaces/${ws}/documents/search?q=${encodeURIComponent(q)}&limit=${limit}${type ? `&type=${encodeURIComponent(type)}` : ''}`
    ),

  getBrokenLinks: (ws: string) =>
    api.get<BrokenLinkBloc[]>(`/workspaces/${ws}/broken-links`),

  getBrokenLinksDetail: (ws: string, blocId: string) =>
    api.get<BrokenLinkDetail[]>(`/workspaces/${ws}/blocs/${blocId}/broken-links`),

  getBacklinks: (ws: string, docId: string, limit = 50) =>
    api.get<BacklinkOut[]>(`/workspaces/${ws}/documents/${docId}/backlinks?limit=${limit}`),
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
  /** Journal de livraison (renseignés par le listing). */
  last_delivery_at: string | null
  last_delivery_status: number | null
  last_delivery_error: string | null
  failures_24h: number
}

export interface WebhookTestOut {
  status_code: number | null
  error: string | null
  /** Temps de réponse de la cible, en ms. */
  duration_ms: number
}

export const ALL_EVENTS = ['document.created', 'document.updated', 'document.deleted'] as const
export type WebhookEvent = (typeof ALL_EVENTS)[number]

// ── Auth / me ───────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string
  email: string
  label: string
  is_admin: boolean
  validated: boolean
  disabled: boolean
}

export interface AppUserOut {
  id: string
  email: string
  label: string
  username: string | null
  source: 'local' | 'oidc'
  is_admin: boolean
  validated: boolean
  disabled: boolean
  has_local_password: boolean
  created_at: string
  updated_at: string
  /** Dernière connexion réussie (local ou OIDC) ; null = jamais. */
  last_login_at: string | null
  /** Workspaces accessibles (membre ou owner). */
  workspaces_count: number
}

/** Décode le payload JWT localement (sans vérification — le serveur valide). */
export function isSuperAdmin(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const segment = token.split('.')[1]
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const payload = JSON.parse(atob(padded))
    return Boolean(payload.is_admin)
  } catch {
    return false
  }
}

export interface InviteCreated {
  user_id: string
  email: string
  /** Chemin à copier — le jeton n'apparaît qu'ici, une seule fois. */
  invite_path: string
  expires_at: string
}

export const usersApi = {
  list: () => api.get<AppUserOut[]>('/admin/users'),
  /** Invitation par lien à usage unique (docflow n'envoie pas d'e-mail). */
  invite: (body: { email: string; label: string; is_admin?: boolean }) =>
    api.post<InviteCreated>('/admin/users/invite', body),
  validate: (id: string) => api.post<AppUserOut>(`/admin/users/${id}/validate`, {}),
  unvalidate: (id: string) => api.post<AppUserOut>(`/admin/users/${id}/unvalidate`, {}),
  /** Rôle et état — le garde anti-lock-out du backend refuse de démonter le
   *  dernier admin local connectable. */
  update: (id: string, body: { is_admin?: boolean; disabled?: boolean }) =>
    api.patch<AppUserOut>(`/admin/users/${id}`, body),
  delete: (id: string) => api.delete(`/admin/users/${id}`),
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
  /** Automates dont un header référence ce secret. */
  used_by_automations: number
  /** Webhooks dont un header référence ce secret. */
  used_by_webhooks: number
}

export interface WalletCheckOut {
  ok: boolean
  error: string | null
  expires_at: string | null
}

export const vaultApi = {
  listWallets: () => api.get<VaultWalletOut[]>('/admin/vault/wallets'),
  createWallet: (body: { name: string; api_key: string }) =>
    api.post<VaultWalletOut>('/admin/vault/wallets', body),
  /** Teste la clé auprès de Harpocrate — l'état du jeton, jamais la clé. */
  checkWallet: (id: string) =>
    api.post<WalletCheckOut>(`/admin/vault/wallets/${id}/check`, {}),
  deleteWallet: (id: string) => api.delete(`/admin/vault/wallets/${id}`),
}

export const secretsApi = {
  list: () => api.get<VaultSecretOut[]>('/admin/secrets'),
  /** Référence à coller dans un header d'automate — jamais la valeur. */
  refOf: (id: string) => `\${secret://${id}}`,
  create: (body: { label: string; slug: string; value: string }) =>
    api.post<VaultSecretOut>('/admin/secrets', body),
  delete: (id: string) => api.delete(`/admin/secrets/${id}`),
}

// ── Mon profil ───────────────────────────────────────────────────────────────

export interface MeProfileOut {
  id: string
  email: string
  username: string | null
  label: string
  source: string
  is_admin: boolean
  /** GUID d'identité OBO (null = appels MCP non attribués). */
  identity: string | null
}

export const meApi = {
  get: () => api.get<MeProfileOut>('/me/profile'),
  update: (body: { email?: string; identity?: string }) =>
    api.patch<MeProfileOut>('/me/profile', body),
}

// ── Secrets HMAC (par utilisateur ; valeur copiable par le propriétaire) ──────

export interface HmacSecretOut {
  id: string
  slug: string
  label: string
  created_at: string
  updated_at: string
}

export interface HmacSecretCreated extends HmacSecretOut {
  /** Valeur renvoyée UNE fois à la création (copie immédiate). */
  value: string
}

export const hmacSecretsApi = {
  list: () => api.get<HmacSecretOut[]>('/hmac-secrets'),
  /** value omis → généré côté serveur. */
  create: (body: { label: string; slug: string; value?: string }) =>
    api.post<HmacSecretCreated>('/hmac-secrets', body),
  /** Re-révèle la valeur (bouton copier). Réservé au propriétaire. */
  reveal: (id: string) => api.get<{ value: string }>(`/hmac-secrets/${id}/reveal`),
  delete: (id: string) => api.delete(`/hmac-secrets/${id}`),
}

// ── OIDC admin ──────────────────────────────────────────────────────────────

export interface OidcConfigOut {
  id: string
  issuer: string
  client_id: string
  enabled: boolean
  /** Mode OIDC-only — sans effet tant que enabled est false. */
  disable_local_login: boolean
  created_at: string
  updated_at: string
}

export const oidcApi = {
  get: () => api.get<OidcConfigOut | null>('/admin/oidc'),
  set: (body: {
    issuer: string
    client_id: string
    disable_local_login?: boolean
    client_secret_ref: string
    enabled: boolean
  }) => api.put<OidcConfigOut>('/admin/oidc', body),
}

// ── Producteur d'events workflow ─────────────────────────────────────────────

export interface EventsProducerConfigOut {
  enabled: boolean
  ingestion_url: string | null
  source_id: string | null
  source_uri: string
  allowed_events: string[]
  /** Le secret HMAC n'est jamais renvoyé — seul ce booléen l'indique. */
  secret_configured: boolean
}

export interface EventsProducerUpdate {
  enabled?: boolean
  ingestion_url?: string | null
  source_id?: string | null
  source_uri?: string | null
  /** Référence vault ${vault://...} — jamais le secret en clair. */
  secret_ref?: string | null
  allowed_events?: string[]
}

export interface EventCatalogEntry {
  eventCode: string
  latestVersion: number
  title: string
  description: string
  deprecated: boolean
}

export interface EventCatalog {
  revision: string
  specVersion: string
  events: EventCatalogEntry[]
}

export const eventsProducerApi = {
  get: () => api.get<EventsProducerConfigOut>('/admin/events-producer'),
  update: (body: EventsProducerUpdate) =>
    api.put<EventsProducerConfigOut>('/admin/events-producer', body),
  testConnection: () =>
    api.post<{ status: number; ok: boolean }>('/admin/events-producer/test-connection', {}),
  /** Catalogue des eventCode émis (contrat producteur exposé via /api/schemas). */
  catalog: () => api.get<EventCatalog>('/schemas'),
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

export interface AuthHeaderRequirement {
  header: string
  value_prefix: string
  scheme_name: string
  scheme_type: string
}

export interface OperationOut {
  operation_id: string | null
  method: string
  path: string
  summary: string | null
  parameters: object[]
  request_body: object | null
  body_skeleton: Record<string, unknown> | null
  auth_headers: AuthHeaderRequirement[]
}

export interface ContractDetailOut {
  contract: ContractOut
  operations: OperationOut[]
  servers: string[]
}

export interface OrphanedOperation {
  operation_id: string
  automations: string[]
}

export interface ContractRefreshOut {
  contract: ContractOut
  /** Opérations disparues du contrat rafraîchi mais encore utilisées. */
  orphaned_operations: OrphanedOperation[]
}

export const contractsApi = {
  list: () => api.get<ContractOut[]>('/admin/contracts'),
  import: (body: { label: string; source_url?: string; raw_spec: object }) =>
    api.post<ContractOut>('/admin/contracts', body),
  detail: (id: string) => api.get<ContractDetailOut>(`/admin/contracts/${id}`),
  spec: (id: string) => api.get<Record<string, unknown>>(`/admin/contracts/${id}/spec`),
  refresh: (id: string) => api.post<ContractRefreshOut>(`/admin/contracts/${id}/refresh`, {}),
  delete: (id: string) => api.delete(`/admin/contracts/${id}`),
}

// ── Automates ───────────────────────────────────────────────────────────────

export interface AutomationHeaderIn {
  name: string
  value?: string | null
  secret_ref?: string | null
  value_prefix?: string | null
  required?: boolean
  enabled?: boolean
}

export interface AutomationHeaderOut {
  id: string
  name: string
  value: string | null
  secret_ref: string | null
  value_prefix: string | null
  required: boolean
  enabled: boolean
}

export interface AutomationOut {
  /** Dernière exécution — renseignées par le listing, null sinon. */
  last_run_at?: string | null
  last_run_status?: string | null
  last_run_http_status?: number | null
  id: string
  workspace_technical_key: string
  label: string
  active: boolean
  pending_count: number
  /** Position d'évaluation dans le workspace demandé (1..n). */
  position: number
  workspace_slugs: string[]
  event_codes: string[]
  block_slugs: string[]
  stop_chain: boolean
  functional_type_slugs: string[]
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
  workspace_slugs?: string[]
  event_codes?: string[]
  block_slugs?: string[]
  stop_chain?: boolean
  functional_type_slugs?: string[]
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
  document_ref: string | null
  document_version: number | null
  change_log_seq: number
  status: string
  executed_at: string
  http_status: number | null
  url: string | null
  request_body: string | null
  response_body: string | null
  event_code: string | null
  manual: boolean
}

/** Automates : objets d'INSTANCE (une règle couvre plusieurs workspaces).
 *  Routes globales /automations — réservées aux admins côté backend. */
export const automationsApi = {
  list: () => api.get<AutomationOut[]>('/automations'),
  create: (body: AutomationCreate) => api.post<AutomationOut>('/automations', body),
  get: (id: string) => api.get<AutomationOut>(`/automations/${id}`),
  update: (id: string, body: Partial<AutomationCreate>) =>
    api.patch<AutomationOut>(`/automations/${id}`, body),
  delete: (id: string) => api.delete(`/automations/${id}`),
  listRuns: (id: string, limit = 50) =>
    api.get<AutomationRunOut[]>(`/automations/${id}/runs?limit=${limit}`),
  replay: (id: string, runId: string) =>
    api.post<AutomationRunOut>(`/automations/${id}/runs/${runId}/replay`, {}),
  runNext: (id: string) =>
    api.post<{
      status: string
      http_status?: number | null
      body?: string | null
      event_code?: string
      event_seq?: number
    }>(`/automations/${id}/run-next`, {}),
  advance: (id: string) =>
    api.post<{
      status: string
      http_status?: number | null
      body?: string | null
      event_code?: string
      event_seq?: number
      advanced?: boolean
    }>(`/automations/${id}/advance`, {}),
  cursorBack: (id: string) =>
    api.post<{ cursor: number }>(`/automations/${id}/cursor-back`, {}),
  /** Ordre global d'évaluation (projeté sur chaque workspace couvert). */
  reorder: (ids: string[]) => api.put<AutomationOut[]>('/automations/order', { ids }),
  /** Clone (config + portée + headers), créé désactivé. */
  clone: (id: string) => api.post<AutomationOut>(`/automations/${id}/clone`, {}),
  /** Vide l'historique d'exécutions (le curseur est conservé). */
  clearRuns: (id: string) => api.delete<{ deleted: number }>(`/automations/${id}/runs`),
  /** Émet des events de modification synthétiques (re-déclenchement d'automates). */
  pushEvents: (selections: { workspace_slug: string; block_slugs?: string[] }[]) =>
    api.post<{
      events: number
      details: { workspace_slug: string; block_slugs: string[]; events: number }[]
    }>('/automations/push-events', { selections }),
}

// ── API Keys ─────────────────────────────────────────────────────────────────

export interface ApiProfileOut {
  id: string
  name: string
  description: string | null
  is_admin: boolean
  created_at: string
  updated_at: string
  scope_count: number
  key_count: number
}

export interface ApiProfileScopeIn {
  workspace_slug: string
  block_slug: string | null
  read_only: boolean
}

export interface ApiProfileScopeOut {
  id: string
  workspace_slug: string
  block_slug: string | null
  read_only: boolean
}

export interface ApiProfileDetail extends ApiProfileOut {
  scopes: ApiProfileScopeOut[]
}

export interface ApiKeyOut {
  id: string
  profile_id: string
  profile_name: string
  label: string
  key_prefix: string
  created_at: string
  last_used_at: string | null
  revoked: boolean
}

export interface ApiKeyCreated extends ApiKeyOut {
  key: string
}

export const apiProfilesApi = {
  list: () => api.get<ApiProfileOut[]>('/user/api-profiles'),
  create: (body: { name: string; description?: string | null; is_admin?: boolean }) =>
    api.post<ApiProfileOut>('/user/api-profiles', body),
  update: (id: string, body: { name?: string; description?: string | null; is_admin?: boolean }) =>
    api.patch<ApiProfileOut>(`/user/api-profiles/${id}`, body),
  get: (id: string) => api.get<ApiProfileDetail>(`/user/api-profiles/${id}`),
  setScopes: (id: string, scopes: ApiProfileScopeIn[]) =>
    api.put<ApiProfileScopeOut[]>(`/user/api-profiles/${id}/scopes`, { scopes }),
  delete: (id: string) => api.delete(`/user/api-profiles/${id}`),
}

export const apiKeysApi = {
  list: () => api.get<ApiKeyOut[]>('/user/api-keys'),
  generate: (body: { profile_id: string; label: string }) =>
    api.post<ApiKeyCreated>('/user/api-keys', body),
  revoke: (id: string) => api.delete(`/user/api-keys/${id}`),
}

// ── Remote certificates ───────────────────────────────────────────────────────

export interface RemoteCertificateOut {
  id: string
  slug: string
  label: string
  cert_type: 'ssh_key' | 'tls'
  public_part: string
  fingerprint: string | null
  expires_at: string | null
  created_at: string
}

export const remoteCertsApi = {
  list: () => api.get<RemoteCertificateOut[]>('/admin/remote/certificates'),
  create: (body: {
    slug: string; label: string; cert_type: 'ssh_key' | 'tls'
    public_part: string; private_key: string; expires_at?: string | null
  }) => api.post<RemoteCertificateOut>('/admin/remote/certificates', body),
  get: (slug: string) => api.get<RemoteCertificateOut>(`/admin/remote/certificates/${slug}`),
  delete: (slug: string) => api.delete(`/admin/remote/certificates/${slug}`),
  /** Génération côté serveur (clé SSH ou certificat TLS auto-signé) : la clé
   *  privée est chiffrée en base et n'est jamais renvoyée. */
  generate: (body: RemoteCertificateGenerateBody) =>
    api.post<RemoteCertificateOut>('/admin/remote/certificates/generate', body),
}

// ── Remote points ─────────────────────────────────────────────────────────────

export type PointType = 'ftp' | 'ftps' | 'sftp' | 'git'
export type AuthType = 'password' | 'pat' | 'certificate'
export type AuthStorage = 'local' | 'vault'
export type GitProvider = 'github' | 'gitlab' | 'gitea' | 'custom'

export interface RemotePointOut {
  id: string
  slug: string
  label: string
  point_type: PointType
  host: string
  port: number | null
  username: string
  git_provider: GitProvider | null
  git_repo: string | null
  git_branch: string
  auth_type: AuthType
  auth_storage: AuthStorage | null
  auth_vault_ref: string | null
  certificate_slug: string | null
  has_local_secret: boolean
  created_at: string
  updated_at: string
}

export interface RemotePointBody {
  slug?: string
  label: string
  point_type: PointType
  host: string
  port?: number | null
  username: string
  git_provider?: GitProvider | null
  git_repo?: string | null
  git_branch?: string
  auth_type: AuthType
  auth_storage?: AuthStorage | null
  auth_secret?: string | null
  auth_vault_ref?: string | null
  certificate_slug?: string | null
}

export interface RemotePointTestResult {
  ok: boolean
  detail: string
}

export const remotePointsApi = {
  list: () => api.get<RemotePointOut[]>('/admin/remote/points'),
  create: (body: RemotePointBody & { slug: string }) =>
    api.post<RemotePointOut>('/admin/remote/points', body),
  get: (slug: string) => api.get<RemotePointOut>(`/admin/remote/points/${slug}`),
  update: (slug: string, body: RemotePointBody) =>
    api.put<RemotePointOut>(`/admin/remote/points/${slug}`, body),
  delete: (slug: string) => api.delete(`/admin/remote/points/${slug}`),
  test: (slug: string) => api.post<RemotePointTestResult>(`/admin/remote/points/${slug}/test`, {}),
}

// ── Backup jobs ───────────────────────────────────────────────────────────────

export interface BackupJobOut {
  id: string
  slug: string
  label: string
  strategy: 'db_dump' | 'git_sync'
  enabled: boolean
  remote_point_slug: string
  workspace_slug: string | null
  schedule_cron: string | null
  schedule_every_seconds: number | null
  git_base_path: string | null
  include_restore_env: boolean
  retention_count: number | null
  created_at: string
  updated_at: string
  last_run_at: string | null
  last_run_status: 'running' | 'success' | 'error' | null
}

export interface BackupJobRunOut {
  id: string
  job_id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'error'
  error_message: string | null
  last_change_seq: number | null
  files_written: number | null
  files_deleted: number | null
  commit_sha: string | null
}

export interface BackupJobBody {
  slug?: string
  label: string
  strategy: 'db_dump' | 'git_sync'
  enabled?: boolean
  remote_point_slug: string
  workspace_slug?: string | null
  schedule_cron?: string | null
  schedule_every_seconds?: number | null
  git_base_path?: string | null
  /** Dump uniquement : dépose <dump>.key (clé de chiffrement, JWT, DSN) à côté de l'archive. */
  include_restore_env?: boolean
  /** Dump uniquement : nombre d'archives à conserver sur le remote (null = tout garder). */
  retention_count?: number | null
}

export const backupApi = {
  listJobs: () => api.get<BackupJobOut[]>('/admin/backup/jobs'),
  createJob: (body: BackupJobBody & { slug: string }) =>
    api.post<BackupJobOut>('/admin/backup/jobs', body),
  getJob: (slug: string) => api.get<BackupJobOut>(`/admin/backup/jobs/${slug}`),
  /** slug et strategy sont immuables : le backend (extra=forbid) les rejette du corps. */
  updateJob: (slug: string, body: Omit<BackupJobBody, 'slug' | 'strategy'>) =>
    api.put<BackupJobOut>(`/admin/backup/jobs/${slug}`, body),
  deleteJob: (slug: string) => api.delete(`/admin/backup/jobs/${slug}`),
  listRuns: (slug: string) => api.get<BackupJobRunOut[]>(`/admin/backup/jobs/${slug}/runs`),
  runJob: (slug: string) => api.post<BackupJobRunOut>(`/admin/backup/jobs/${slug}/run`, {}),
  /** Réalimente l'instance depuis le miroir git d'un remote point (additif, idempotent). */
  restoreGit: (body: { remote_point_slug: string; git_base_path?: string | null; workspace?: string | null }) =>
    api.post<RestoreGitReport>('/admin/backup/restore-git', body),
}

export interface RestoreGitReport {
  workspaces_created: number
  blocks_created: number
  types_imported: number
  docs_created: number
  docs_updated: number
  errors: string[]
}

export interface RemoteCertificateGenerateBody {
  slug: string
  label: string
  cert_type?: 'ssh_key' | 'tls'
  common_name?: string | null
  expires_at?: string | null
}

// ── Setup wizard ─────────────────────────────────────────────────────────────

export interface AuthMethodsOut {
  local: boolean
  oidc: boolean
  needs_setup: boolean
}

export interface InitAdminRequest {
  username: string
  email: string
  password: string
}

/** Flux public d'invitation (sans authentification). */
export const inviteApi = {
  info: (token: string) =>
    api.get<{ email: string; label: string }>(`/invite/${encodeURIComponent(token)}`),
  accept: (token: string, password: string) =>
    api.post<void>(`/invite/${encodeURIComponent(token)}`, { password }),
}

export const setupApi = {
  methods: () => api.get<AuthMethodsOut>('/auth/methods'),
  initAdmin: (body: InitAdminRequest) => api.post<{ id: string }>('/setup/init-admin', body),
}

// ── Login OIDC (endpoints publics) ───────────────────────────────────────────

export interface OidcPublicConfig {
  issuer: string
  client_id: string
  enabled: boolean
  authorization_endpoint: string | null
}

export interface OidcCallbackRequest {
  code: string
  redirect_uri: string
  nonce?: string
}

export const oidcLoginApi = {
  config: () => api.get<OidcPublicConfig | null>('/auth/oidc/config'),
  callback: (body: OidcCallbackRequest) =>
    api.post<{ access_token: string; token_type: string }>('/auth/oidc/callback', body),
}
