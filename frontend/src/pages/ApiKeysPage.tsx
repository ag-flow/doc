import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CaretDown, CaretRight, Copy, Check, Trash, Plus, Key, ShieldCheck, Plug,
} from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { HmacSecretsTab } from '../components/HmacSecretsTab'
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
      className={`tag cursor-pointer border-0 transition-opacity hover:opacity-75 ${
        value ? 'tag-neutral' : 'tag-accent'
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
    <div className="rounded-md border border-[var(--color-divider)] bg-surface">
      <div className="flex items-center gap-3 px-3 py-2">
        <input type="checkbox" checked={wsEnabled} onChange={toggleWs} />
        <button
          type="button"
          className="flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0
            text-left text-ink/[0.75] hover:text-ink"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded
            ? <CaretDown size={14} weight="duotone" />
            : <CaretRight size={14} weight="duotone" />}
          <span className="text-[12px] [font-family:var(--font-mono)]">{ws.slug}</span>
          <span className="text-[13px] text-ink/[0.55]">{ws.label}</span>
        </button>
        <span className="ml-auto text-[11px] text-ink/[0.45]">tout le workspace</span>
        {wsEnabled && (
          <ReadOnlyToggle
            value={wsReadOnly}
            onChange={(v) => onToggle(wsKey, true, v)}
          />
        )}
      </div>
      {expanded && (
        <div className="space-y-1 border-t border-[var(--color-divider)] bg-ink/[0.03] px-6 py-2">
          {blocks.length === 0 && (
            <p className="m-0 text-[12px] text-ink/[0.45]">Aucun bloc dans ce workspace</p>
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
                />
                <span className="text-[12px] text-ink/[0.75] [font-family:var(--font-mono)]">
                  {b.slug}
                </span>
                <span className="text-[12px] text-ink/[0.55]">{b.label}</span>
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
      void qc.invalidateQueries({ queryKey: ['api-profile', profile.id] })
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
    <div className="rounded-md border border-[var(--color-divider)] bg-surface">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          className="flex flex-1 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-left"
          onClick={() => { setExpanded((v) => !v); setScopesLoaded(false) }}
        >
          {expanded
            ? <CaretDown size={16} weight="duotone" />
            : <CaretRight size={16} weight="duotone" />}
          <span className="text-[15px] font-[600] [font-family:var(--font-heading)]">
            {profile.name}
          </span>
          {profile.is_admin && (
            <span className="tag tag-accent gap-1">
              <ShieldCheck size={11} weight="duotone" />
              Admin
            </span>
          )}
          {profile.description && (
            <span className="text-[13px] text-ink/[0.55]">{profile.description}</span>
          )}
          <span className="ml-auto text-[11px] text-ink/[0.45]">
            {profile.scope_count} scope{profile.scope_count !== 1 ? 's' : ''} ·{' '}
            {profile.key_count} clé{profile.key_count !== 1 ? 's' : ''} active{profile.key_count !== 1 ? 's' : ''}
          </span>
        </button>
        {!confirmDelete ? (
          <Button
            variant="icon"
            size="sm"
            className="text-accent-2-700"
            onClick={() => setConfirmDelete(true)}
            title="Supprimer le profil"
          >
            <Trash size={14} weight="duotone" />
          </Button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-accent-2-700">Supprimer ?</span>
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
        <div className="space-y-3 border-t border-[var(--color-divider)] px-4 py-4">
          <div className="field">
            <label htmlFor={`desc-${profile.id}`}>Description</label>
            <div className="flex items-center gap-2">
              <Input
                id={`desc-${profile.id}`}
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
              {descMsg && <span className="text-[12px] text-accent-700">{descMsg}</span>}
            </div>
          </div>

          <p className="m-0 text-[11px] uppercase tracking-[0.08em] text-ink/[0.6]">Scopes</p>
          {workspaces.length === 0 ? (
            <p className="m-0 text-[13px] text-ink/[0.45]">Aucun workspace disponible</p>
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
            {saveMsg && <span className="text-[13px] text-accent-700">{saveMsg}</span>}
            {saveScopesMutation.isError && (
              <span className="text-[13px] text-accent-2-700">Erreur lors de l'enregistrement</span>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-[var(--color-divider)] pt-3">
            <input
              id={`admin-${profile.id}`}
              type="checkbox"
              checked={profile.is_admin}
              onChange={(e) => toggleAdminMutation.mutate(e.target.checked)}
              disabled={toggleAdminMutation.isPending}
            />
            <label
              htmlFor={`admin-${profile.id}`}
              className="flex cursor-pointer items-center gap-1.5 text-[14px]"
            >
              <ShieldCheck size={14} weight="duotone" className="text-accent-700" />
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

  if (isLoading) return <TableSkeleton rows={3} columns={3} />

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => { setShowCreate((v) => !v); setCreateError(null) }}>
          <Plus size={15} weight="duotone" />
          Nouveau profil
        </Button>
      </div>

      {showCreate && (
        <form
          className="space-y-3 rounded-md border border-[var(--color-divider)] bg-surface p-4"
          onSubmit={(e) => { e.preventDefault(); createMutation.mutate() }}
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nom *" htmlFor="new-profile-name">
              <Input
                id="new-profile-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Mon profil API"
                required
              />
            </Field>
            <Field label="Description" htmlFor="new-profile-desc">
              <Input
                id="new-profile-desc"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Optionnel"
              />
            </Field>
          </div>
          <div className="flex items-center gap-2">
            <input
              id="new-is-admin"
              type="checkbox"
              checked={newIsAdmin}
              onChange={(e) => setNewIsAdmin(e.target.checked)}
            />
            <label
              htmlFor="new-is-admin"
              className="flex cursor-pointer items-center gap-1.5 text-[14px]"
            >
              <ShieldCheck size={14} weight="duotone" className="text-accent-700" />
              Profil admin — accès complet (tous workspaces, create_workspace, import_template, create_block)
            </label>
          </div>
          <div aria-live="polite" className="empty:hidden">
            {createError && <p className="field-error m-0">{createError}</p>}
          </div>
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
        <EmptyState message="Aucun profil. Créez-en un pour commencer." />
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
    <div className="dialog-backdrop z-50">
      <div className="dialog" role="dialog" aria-modal="true">
        <h4 className="dialog-title m-0">Générer une clé API</h4>

        {!generated ? (
          <form
            onSubmit={(e) => { e.preventDefault(); generateMutation.mutate() }}
            className="contents"
          >
            <Field label="Profil *" htmlFor="generate-profile">
              <select
                id="generate-profile"
                className="input"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
                required
              >
                <option value="">— Choisir un profil —</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Label *" htmlFor="generate-label">
              <Input
                id="generate-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="ex. script-ci, intégration-x"
                required
              />
            </Field>
            <div aria-live="polite" className="empty:hidden">
              {error && <p className="field-error m-0">{error}</p>}
            </div>
            <div className="dialog-actions">
              <Button variant="secondary" type="button" onClick={onClose}>
                Annuler
              </Button>
              <Button type="submit" disabled={!profileId || !label || generateMutation.isPending}>
                Générer
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className="dialog-body m-0 text-accent-700">Clé générée avec succès !</p>
            <div className="flex items-center gap-2">
              <p className="m-0 min-w-0 flex-1 break-all rounded-md bg-neutral-100 p-3 text-[12px]
                [font-family:var(--font-mono)] select-all">
                {generated.key}
              </p>
              <Button variant="secondary" size="sm" className="shrink-0" onClick={() => void copyKey()}>
                {copied
                  ? <Check size={14} weight="duotone" className="text-accent-700" />
                  : <Copy size={14} weight="duotone" />}
                {copied ? 'Copié' : 'Copier'}
              </Button>
            </div>
            <p className="m-0 text-[13px] text-accent-2-700">
              ⚠ Cette clé ne sera plus affichée après fermeture de cette fenêtre.
            </p>
            <div className="dialog-actions">
              <Button onClick={onClose}>Fermer</Button>
            </div>
          </>
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

  if (isLoading) return <TableSkeleton rows={4} columns={6} />

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setShowGenerate(true)}>
          <Key size={15} weight="duotone" />
          Générer une clé
        </Button>
      </div>

      {keys.length === 0 ? (
        <EmptyState message="Aucune clé. Créez un profil et générez une clé pour commencer." />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Préfixe</th>
              <th>Label</th>
              <th>Profil</th>
              <th>Créée le</th>
              <th>Dernière utilisation</th>
              <th>Statut</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id}>
                <td className="text-[12px] text-ink/[0.75] [font-family:var(--font-mono)]">
                  {k.key_prefix}…
                </td>
                <td>{k.label}</td>
                <td className="text-ink/[0.55]">{k.profile_name}</td>
                <td className="text-ink/[0.55]">{fmtDate(k.created_at)}</td>
                <td className="text-ink/[0.55]">
                  {k.last_used_at ? fmtDate(k.last_used_at) : '—'}
                </td>
                <td>
                  <span className={`tag ${k.revoked ? 'tag-accent-2' : 'tag-accent'}`}>
                    {k.revoked ? 'Révoquée' : 'Active'}
                  </span>
                </td>
                <td className="whitespace-nowrap text-right">
                  {!k.revoked && revokeTarget !== k.id && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-accent-2-700"
                      onClick={() => setRevokeTarget(k.id)}
                    >
                      Révoquer
                    </Button>
                  )}
                  {!k.revoked && revokeTarget === k.id && (
                    <div className="flex items-center justify-end gap-2">
                      <span className="text-[12px] text-accent-2-700">Confirmer ?</span>
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
      )}

      {showGenerate && <GenerateKeyModal onClose={() => setShowGenerate(false)} />}
    </div>
  )
}

// ── MCP URL banner ────────────────────────────────────────────────────────────

function McpUrlBanner() {
  const mcpUrl = `${window.location.origin}/api/mcp/sse`
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(mcpUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="mb-8">
      <p className="m-0 flex items-center gap-1.5 text-[15px] font-[600] [font-family:var(--font-heading)]">
        <Plug size={16} weight="duotone" className="text-accent-700" />
        Serveur MCP
      </p>
      <p className="mb-2 mt-1 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        Connectez vos outils IA (Claude Desktop, Cursor…) à cette instance docflow via le protocole MCP.
      </p>
      <div className="flex max-w-[640px] items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md bg-neutral-100 px-3 py-2 text-[12px]
          [font-family:var(--font-mono)] select-all">
          {mcpUrl}
        </code>
        <span className="tag tag-neutral shrink-0 [font-family:var(--font-mono)]">sse</span>
        <Button variant="secondary" size="sm" className="shrink-0" onClick={() => void copy()}>
          {copied
            ? <Check size={13} weight="duotone" className="text-accent-700" />
            : <Copy size={13} weight="duotone" />}
          {copied ? 'Copié' : 'Copier'}
        </Button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = 'profiles' | 'keys' | 'hmac'

export function ApiKeysPage() {
  const [activeTab, setActiveTab] = useState<Tab>('profiles')

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title="Clés API" />
      <McpUrlBanner />

      {/* Onglets à filet cyan */}
      <div className="mb-6 flex gap-1 border-b border-[var(--color-divider)]">
        {([['profiles', 'Profils API'], ['keys', 'Clés API'], ['hmac', 'HMAC']] as [Tab, string][]).map(
          ([tab, label]) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`border-0 border-b-2 bg-transparent px-4 py-2 text-[14px] font-[600]
                [font-family:var(--font-heading)] [border-bottom-style:solid] transition-colors ${
                  activeTab === tab
                    ? 'border-b-accent text-accent-700'
                    : 'border-b-transparent text-ink/[0.55] hover:text-ink'
                }`}
              data-testid={`apikeys-tab-${tab}`}
            >
              {label}
            </button>
          )
        )}
      </div>

      {activeTab === 'profiles' && <ProfilesTab />}
      {activeTab === 'keys' && <KeysTab />}
      {activeTab === 'hmac' && <HmacSecretsTab />}
    </div>
  )
}
