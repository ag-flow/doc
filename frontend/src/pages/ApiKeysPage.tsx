import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Copy, Check, Trash2, Plus, Key, ShieldCheck, Plug } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  api,
  apiProfilesApi,
  apiKeysApi,
  type ApiProfileOut,
  type ApiProfileDetail,
  type ApiProfileScopeIn,
  type ApiKeyOut,
  type ApiKeyCreated,
  type WorkspaceOut,
  type DataBlockOut,
} from '../lib/api'

// ── Scope state helpers ───────────────────────────────────────────────────────

type ScopeKey = string // `${ws_slug}::${block_slug ?? ''}`

function scopeKey(ws: string, block?: string | null): ScopeKey {
  return `${ws}::${block ?? ''}`
}

function toScopeList(map: Map<ScopeKey, boolean>): ApiProfileScopeIn[] {
  const result: ApiProfileScopeIn[] = []
  for (const [key, read_only] of map.entries()) {
    const sep = key.indexOf('::')
    const ws = key.slice(0, sep)
    const block = key.slice(sep + 2) || null
    result.push({ workspace_slug: ws, block_slug: block, read_only })
  }
  return result
}

function fromScopeList(scopes: ApiProfileScopeIn[]): Map<ScopeKey, boolean> {
  const m = new Map<ScopeKey, boolean>()
  for (const s of scopes) {
    m.set(scopeKey(s.workspace_slug, s.block_slug), s.read_only)
  }
  return m
}

// ── Date helpers ─────────────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

// ── Scope editor ─────────────────────────────────────────────────────────────

function ReadOnlyToggle({
  value,
  onChange,
}: {
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
        value
          ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
          : 'bg-green-100 text-green-700 hover:bg-green-200'
      }`}
    >
      {value ? 'Lecture seule' : 'Lect./Écriture'}
    </button>
  )
}

function WorkspaceScopeRow({
  ws,
  scopes,
  onToggle,
}: {
  ws: WorkspaceOut
  scopes: Map<ScopeKey, boolean>
  onToggle: (key: ScopeKey, enabled: boolean, readOnly: boolean) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const wsKey = scopeKey(ws.slug)
  const wsEnabled = scopes.has(wsKey)
  const wsReadOnly = scopes.get(wsKey) ?? true

  const { data: blocks = [] } = useQuery<DataBlockOut[]>({
    queryKey: ['blocks', ws.slug],
    queryFn: () => api.get<DataBlockOut[]>(`/workspaces/${ws.slug}/blocks`),
    enabled: expanded,
  })

  function toggleWs() {
    onToggle(wsKey, !wsEnabled, wsReadOnly)
  }

  function toggleBlock(block_slug: string, enabled: boolean, readOnly: boolean) {
    onToggle(scopeKey(ws.slug, block_slug), enabled, readOnly)
  }

  return (
    <div className="rounded border border-gray-200 bg-white">
      <div className="flex items-center gap-3 px-3 py-2">
        <input
          type="checkbox"
          checked={wsEnabled}
          onChange={toggleWs}
          className="h-4 w-4 rounded border-gray-300 text-indigo-600"
        />
        <button
          type="button"
          className="flex items-center gap-1 text-sm font-medium text-gray-700 hover:text-gray-900"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span className="font-mono text-xs">{ws.slug}</span>
          <span className="text-gray-500">{ws.label}</span>
        </button>
        <span className="ml-auto text-xs text-gray-400">tout le workspace</span>
        {wsEnabled && (
          <ReadOnlyToggle
            value={wsReadOnly}
            onChange={(v) => onToggle(wsKey, true, v)}
          />
        )}
      </div>
      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-6 py-2 space-y-1">
          {blocks.length === 0 && (
            <p className="text-xs text-gray-400">Aucun bloc dans ce workspace</p>
          )}
          {blocks.map((b) => {
            const bKey = scopeKey(ws.slug, b.slug)
            const bEnabled = scopes.has(bKey)
            const bReadOnly = scopes.get(bKey) ?? true
            return (
              <div key={b.slug} className="flex items-center gap-3 py-1">
                <input
                  type="checkbox"
                  checked={bEnabled}
                  onChange={() => toggleBlock(b.slug, !bEnabled, bReadOnly)}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
                <span className="font-mono text-xs text-gray-700">{b.slug}</span>
                <span className="text-xs text-gray-500">{b.label}</span>
                {bEnabled && (
                  <ReadOnlyToggle
                    value={bReadOnly}
                    onChange={(v) => toggleBlock(b.slug, true, v)}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Profile card ──────────────────────────────────────────────────────────────

function ProfileCard({
  profile,
  onDeleted,
}: {
  profile: ApiProfileOut
  onDeleted: () => void
}) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [scopes, setScopes] = useState<Map<ScopeKey, boolean>>(new Map())
  const [scopesLoaded, setScopesLoaded] = useState(false)
  const [desc, setDesc] = useState(profile.description ?? '')
  const [descMsg, setDescMsg] = useState<string | null>(null)

  const { data: detail } = useQuery<ApiProfileDetail>({
    queryKey: ['api-profile', profile.id],
    queryFn: () => apiProfilesApi.get(profile.id),
    enabled: expanded && !scopesLoaded,
  })

  if (detail && !scopesLoaded) {
    setScopes(fromScopeList(detail.scopes))
    setScopesLoaded(true)
  }

  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    enabled: expanded,
  })

  const saveScopesMutation = useMutation({
    mutationFn: () => apiProfilesApi.setScopes(profile.id, toScopeList(scopes)),
    onSuccess: () => {
      setSaveMsg('Scopes enregistrés')
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
      setTimeout(() => setSaveMsg(null), 2000)
    },
  })

  const toggleAdminMutation = useMutation({
    mutationFn: (is_admin: boolean) => apiProfilesApi.update(profile.id, { is_admin }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['api-profiles'] }),
  })

  const saveDescMutation = useMutation({
    mutationFn: () => apiProfilesApi.update(profile.id, { description: desc || null }),
    onSuccess: () => {
      setDescMsg('Description enregistrée')
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
      setTimeout(() => setDescMsg(null), 2000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => apiProfilesApi.delete(profile.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
      onDeleted()
    },
  })

  function handleScopeToggle(key: ScopeKey, enabled: boolean, readOnly: boolean) {
    setScopes((prev) => {
      const next = new Map(prev)
      if (enabled) {
        next.set(key, readOnly)
      } else {
        next.delete(key)
      }
      return next
    })
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          className="flex items-center gap-2 flex-1 text-left"
          onClick={() => { setExpanded((v) => !v); setScopesLoaded(false) }}
        >
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span className="font-medium text-gray-900">{profile.name}</span>
          {profile.is_admin && (
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
              <ShieldCheck size={11} />
              Admin
            </span>
          )}
          {profile.description && (
            <span className="text-sm text-gray-500">{profile.description}</span>
          )}
          <span className="ml-auto text-xs text-gray-400">
            {profile.scope_count} scope{profile.scope_count !== 1 ? 's' : ''} ·{' '}
            {profile.key_count} clé{profile.key_count !== 1 ? 's' : ''} active{profile.key_count !== 1 ? 's' : ''}
          </span>
        </button>
        {!confirmDelete ? (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="p-1 text-gray-400 hover:text-red-500"
            title="Supprimer le profil"
          >
            <Trash2 size={16} />
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-xs text-red-600">Supprimer ?</span>
            <Button
              variant="danger"
              size="sm"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              Oui
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setConfirmDelete(false)}>
              Non
            </Button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="border-t border-gray-100 px-4 py-4 space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Description</label>
            <div className="flex items-center gap-2">
              <Input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="Description optionnelle"
                className="flex-1"
              />
              <Button
                size="sm"
                onClick={() => saveDescMutation.mutate()}
                disabled={saveDescMutation.isPending}
              >
                Enregistrer
              </Button>
              {descMsg && <span className="text-xs text-green-600">{descMsg}</span>}
            </div>
          </div>

          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Scopes</p>
          {workspaces.length === 0 ? (
            <p className="text-sm text-gray-400">Aucun workspace disponible</p>
          ) : (
            <div className="space-y-2">
              {workspaces.map((ws) => (
                <WorkspaceScopeRow
                  key={ws.slug}
                  ws={ws}
                  scopes={scopes}
                  onToggle={handleScopeToggle}
                />
              ))}
            </div>
          )}
          <div className="flex items-center gap-3 pt-2">
            <Button onClick={() => saveScopesMutation.mutate()} disabled={saveScopesMutation.isPending}>
              Enregistrer les scopes
            </Button>
            {saveMsg && <span className="text-sm text-green-600">{saveMsg}</span>}
            {saveScopesMutation.isError && (
              <span className="text-sm text-red-600">Erreur lors de l'enregistrement</span>
            )}
          </div>

          <div className="border-t border-gray-100 pt-3 flex items-center gap-2">
            <input
              id={`admin-${profile.id}`}
              type="checkbox"
              checked={profile.is_admin}
              onChange={(e) => toggleAdminMutation.mutate(e.target.checked)}
              disabled={toggleAdminMutation.isPending}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600"
            />
            <label htmlFor={`admin-${profile.id}`} className="text-sm font-medium text-gray-700 flex items-center gap-1 cursor-pointer">
              <ShieldCheck size={14} className="text-indigo-500" />
              Profil admin — accès complet (tous workspaces, create_workspace, import_template, create_block)
            </label>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Profiles tab ──────────────────────────────────────────────────────────────

function ProfilesTab() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newIsAdmin, setNewIsAdmin] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const { data: profiles = [], isLoading } = useQuery<ApiProfileOut[]>({
    queryKey: ['api-profiles'],
    queryFn: () => apiProfilesApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: () => apiProfilesApi.create({ name: newName, description: newDesc || null, is_admin: newIsAdmin }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
      setShowCreate(false)
      setNewName('')
      setNewDesc('')
      setNewIsAdmin(false)
      setCreateError(null)
    },
    onError: (err: Error) => setCreateError(err.message),
  })

  if (isLoading) return <p className="text-sm text-gray-500">Chargement…</p>

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => { setShowCreate((v) => !v); setCreateError(null) }}>
          <Plus size={16} className="mr-1" />
          Nouveau profil
        </Button>
      </div>

      {showCreate && (
        <form
          className="rounded-lg border border-gray-200 bg-white p-4 space-y-3"
          onSubmit={(e) => { e.preventDefault(); createMutation.mutate() }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Nom *</label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Mon profil API"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Description</label>
              <Input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Optionnel"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              id="new-is-admin"
              type="checkbox"
              checked={newIsAdmin}
              onChange={(e) => setNewIsAdmin(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600"
            />
            <label htmlFor="new-is-admin" className="text-sm font-medium text-gray-700 flex items-center gap-1">
              <ShieldCheck size={14} className="text-indigo-500" />
              Profil admin — accès complet (tous workspaces, create_workspace, import_template, create_block)
            </label>
          </div>
          {createError && <p className="text-sm text-red-600">{createError}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={!newName || createMutation.isPending}>
              Créer
            </Button>
            <Button variant="secondary" type="button" onClick={() => setShowCreate(false)}>
              Annuler
            </Button>
          </div>
        </form>
      )}

      {profiles.length === 0 && !showCreate && (
        <p className="text-sm text-gray-400 text-center py-8">
          Aucun profil. Créez-en un pour commencer.
        </p>
      )}

      {profiles.map((p) => (
        <ProfileCard key={p.id} profile={p} onDeleted={() => void qc.invalidateQueries({ queryKey: ['api-profiles'] })} />
      ))}
    </div>
  )
}

// ── Generate key modal ────────────────────────────────────────────────────────

function GenerateKeyModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [profileId, setProfileId] = useState('')
  const [label, setLabel] = useState('')
  const [generated, setGenerated] = useState<ApiKeyCreated | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: profiles = [] } = useQuery<ApiProfileOut[]>({
    queryKey: ['api-profiles'],
    queryFn: () => apiProfilesApi.list(),
  })

  const generateMutation = useMutation({
    mutationFn: () => apiKeysApi.generate({ profile_id: profileId, label }),
    onSuccess: (data) => {
      setGenerated(data)
      void qc.invalidateQueries({ queryKey: ['api-keys'] })
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  async function copyKey() {
    if (!generated) return
    await navigator.clipboard.writeText(generated.key)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl space-y-4">
        <h2 className="text-lg font-bold">Générer une clé API</h2>

        {!generated ? (
          <form
            onSubmit={(e) => { e.preventDefault(); generateMutation.mutate() }}
            className="space-y-4"
          >
            <div>
              <label className="mb-1 block text-sm font-medium">Profil *</label>
              <select
                className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
                required
              >
                <option value="">— Choisir un profil —</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Label *</label>
              <Input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="ex. script-ci, intégration-x"
                required
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex gap-2">
              <Button type="submit" disabled={!profileId || !label || generateMutation.isPending}>
                Générer
              </Button>
              <Button variant="secondary" type="button" onClick={onClose}>
                Annuler
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-200 bg-green-50 p-3">
              <p className="text-sm font-medium text-green-800 mb-2">Clé générée avec succès !</p>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={generated.key}
                  className="flex-1 rounded border border-gray-300 bg-white px-3 py-2 font-mono text-xs"
                />
                <button
                  type="button"
                  onClick={copyKey}
                  className="flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-2 text-sm hover:bg-gray-50"
                >
                  {copied ? <Check size={14} className="text-green-600" /> : <Copy size={14} />}
                  {copied ? 'Copié' : 'Copier'}
                </button>
              </div>
            </div>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              ⚠ Cette clé ne sera plus affichée après fermeture de cette fenêtre.
            </p>
            <Button onClick={onClose}>Fermer</Button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Keys tab ─────────────────────────────────────────────────────────────────

function KeysTab() {
  const qc = useQueryClient()
  const [showGenerate, setShowGenerate] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null)

  const { data: keys = [], isLoading } = useQuery<ApiKeyOut[]>({
    queryKey: ['api-keys'],
    queryFn: () => apiKeysApi.list(),
  })

  const revokeMutation = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['api-keys'] })
      void qc.invalidateQueries({ queryKey: ['api-profiles'] })
      setRevokeTarget(null)
    },
  })

  if (isLoading) return <p className="text-sm text-gray-500">Chargement…</p>

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setShowGenerate(true)}>
          <Key size={16} className="mr-1" />
          Générer une clé
        </Button>
      </div>

      {keys.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">
          Aucune clé. Créez un profil et générez une clé pour commencer.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Préfixe</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Label</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Profil</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Créée le</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Dernière utilisation</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Statut</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {keys.map((k) => (
                <tr key={k.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{k.key_prefix}…</td>
                  <td className="px-4 py-3 text-gray-700">{k.label}</td>
                  <td className="px-4 py-3 text-gray-500">{k.profile_name}</td>
                  <td className="px-4 py-3 text-gray-500">{fmtDate(k.created_at)}</td>
                  <td className="px-4 py-3 text-gray-500">
                    {k.last_used_at ? fmtDate(k.last_used_at) : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        k.revoked
                          ? 'bg-red-100 text-red-700'
                          : 'bg-green-100 text-green-700'
                      }`}
                    >
                      {k.revoked ? 'Révoquée' : 'Active'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {!k.revoked && revokeTarget !== k.id && (
                      <button
                        type="button"
                        onClick={() => setRevokeTarget(k.id)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Révoquer
                      </button>
                    )}
                    {!k.revoked && revokeTarget === k.id && (
                      <div className="flex items-center gap-2 justify-end">
                        <span className="text-xs text-red-600">Confirmer ?</span>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => revokeMutation.mutate(k.id)}
                          disabled={revokeMutation.isPending}
                        >
                          Oui
                        </Button>
                        <Button variant="secondary" size="sm" onClick={() => setRevokeTarget(null)}>
                          Non
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showGenerate && <GenerateKeyModal onClose={() => setShowGenerate(false)} />}
    </div>
  )
}

// ── MCP URL banner ────────────────────────────────────────────────────────────

function McpUrlBanner() {
  const mcpUrl = `${window.location.origin}/mcp`
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(mcpUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex items-start gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 mb-6">
      <Plug size={16} className="mt-0.5 shrink-0 text-indigo-500" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-indigo-900 mb-1">Serveur MCP</p>
        <p className="text-xs text-indigo-700 mb-2">
          Connectez vos outils IA (Claude Desktop, Cursor…) à cette instance docflow via le protocole MCP.
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 min-w-0 truncate rounded border border-indigo-200 bg-white px-3 py-1.5 font-mono text-xs text-gray-800 select-all">
            {mcpUrl}
          </code>
          <button
            type="button"
            onClick={copy}
            className="shrink-0 flex items-center gap-1 rounded border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            {copied ? <Check size={13} className="text-green-600" /> : <Copy size={13} />}
            {copied ? 'Copié' : 'Copier'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = 'profiles' | 'keys'

export function ApiKeysPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profiles')

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Clés API</h1>
      <McpUrlBanner />

      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {([['profiles', 'Profils API'], ['keys', 'Clés API']] as [Tab, string][]).map(
          ([tab, label]) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {label}
            </button>
          )
        )}
      </div>

      {activeTab === 'profiles' ? <ProfilesTab /> : <KeysTab />}
    </div>
  )
}
