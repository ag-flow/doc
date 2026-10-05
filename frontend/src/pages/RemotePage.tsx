import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CaretDown, CaretRight, CheckCircle, CircleNotch, Clock, Copy, Cpu, GitBranch,
  Globe, HardDrive, Key, MagicWand, Network, Play, Plug, Plus, ShieldCheck,
  Trash, XCircle,
} from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { EmptyState } from '../components/ui/states'
import {
  type BackupJobBody, type BackupJobOut, type BackupJobRunOut,
  type GitProvider, type PointType, type RemoteCertificateOut,
  type RemotePointBody, type RemotePointOut,
  backupApi, remoteCertsApi, remotePointsApi,
} from '../lib/api'

// ─────────────────────────────────────────────────────────────────────────────
// Slugification automatique depuis le label
// ─────────────────────────────────────────────────────────────────────────────

function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD').replace(/\p{M}/gu, '')
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Certificats
// ─────────────────────────────────────────────────────────────────────────────

function CertificatesTab() {
  const qc = useQueryClient()
  const { data: certs = [] } = useQuery({ queryKey: ['remote-certs'], queryFn: remoteCertsApi.list })
  const [showForm, setShowForm] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [gitIdentity, setGitIdentity] = useState('')
  const [form, setForm] = useState({ slug: '', label: '', cert_type: 'ssh_key' as 'ssh_key' | 'tls', public_part: '', private_key: '' })

  function resetForm() {
    setShowForm(false)
    setForm({ slug: '', label: '', cert_type: 'ssh_key', public_part: '', private_key: '' })
    setGitIdentity('')
  }

  const createMut = useMutation({
    mutationFn: () => remoteCertsApi.create(form),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['remote-certs'] })
      resetForm()
    },
    onError: (e) => setErr((e as Error).message),
  })
  // Génération côté serveur (clé ed25519 format OpenSSH — le seul que le
  // client SFTP/git du backend sait relire — ou certificat TLS auto-signé).
  // Le matériel est créé et enregistré directement, la clé privée ne transite
  // jamais par le navigateur.
  const generateMut = useMutation({
    mutationFn: () => remoteCertsApi.generate({
      slug: form.slug,
      label: form.label,
      cert_type: form.cert_type,
      common_name: gitIdentity.trim() || null,
    }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['remote-certs'] })
      resetForm()
    },
    onError: (e) => setErr((e as Error).message),
  })
  const delMut = useMutation({
    mutationFn: (slug: string) => remoteCertsApi.delete(slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['remote-certs'] }),
  })

  function handleCopyPublicKey() {
    void navigator.clipboard.writeText(form.public_part).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="m-0 text-[13px] text-ink/[0.55]">{certs.length} certificat{certs.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => { setShowForm(v => !v); setErr(null) }}>
          <Plus size={14} weight="duotone" />{showForm ? 'Annuler' : 'Ajouter'}
        </Button>
      </div>

      {showForm && (
        <div className="flex flex-col gap-3 border-y border-[var(--color-divider)] py-4">
          <div className="grid grid-cols-2 gap-3">
            <Input placeholder="Label" value={form.label} onChange={e => { const v = e.target.value; setForm(p => ({ ...p, label: v, slug: slugify(v) })) }} />
            <Input placeholder="slug (ex. deploy-key)" value={form.slug} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />
          </div>

          <div className="flex items-center gap-2">
            <select
              className="input flex-1"
              value={form.cert_type}
              onChange={e => setForm(p => ({ ...p, cert_type: e.target.value as 'ssh_key' | 'tls', public_part: '', private_key: '' }))}
            >
              <option value="ssh_key">Clé SSH (git / SFTP)</option>
              <option value="tls">Certificat TLS (FTPS)</option>
            </select>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => { setErr(null); generateMut.mutate() }}
              disabled={generateMut.isPending || !form.slug || !form.label}
              title={form.cert_type === 'ssh_key'
                ? "Génère une paire ed25519 côté serveur et l'enregistre directement — copiez ensuite la clé publique depuis la liste"
                : "Génère un certificat auto-signé (RSA 2048, 10 ans) côté serveur et l'enregistre directement"}
              data-testid="cert-generate"
            >
              {generateMut.isPending
                ? <><CircleNotch size={14} weight="duotone" className="animate-spin" />Génération…</>
                : <><MagicWand size={14} weight="duotone" />Générer</>
              }
            </Button>
          </div>

          <Input
            placeholder={form.cert_type === 'ssh_key'
              ? 'Identité git (commentaire de la clé, ex. deploy@docflow) — optionnel'
              : 'Common Name du certificat (défaut : slug) — optionnel'}
            value={gitIdentity}
            onChange={e => setGitIdentity(e.target.value)}
            data-testid="cert-git-identity"
          />

          <div className="relative">
            <textarea
              rows={4}
              placeholder={form.cert_type === 'ssh_key'
                ? 'Clé publique (ssh-ed25519 …) — pour importer une paire existante, sinon cliquez Générer'
                : 'Certificat PEM (-----BEGIN CERTIFICATE-----) — pour importer un existant, sinon cliquez Générer'}
              className="input resize-none text-[12px] [font-family:var(--font-mono)]"
              value={form.public_part}
              onChange={e => setForm(p => ({ ...p, public_part: e.target.value }))}
            />
            {form.public_part && (
              <button
                type="button"
                onClick={handleCopyPublicKey}
                className="absolute top-2 right-2 flex cursor-pointer items-center gap-1 rounded-md border border-[var(--color-divider)] bg-paper px-2 py-1 text-[11px] text-ink/[0.55] hover:text-ink"
                title="Copier la clé publique (deploy key GitHub / GitLab)"
              >
                <Copy size={12} weight="duotone" />
                {copied ? 'Copié !' : 'Copier'}
              </button>
            )}
          </div>

          <textarea
            rows={6}
            placeholder="Clé privée (chiffrée en base, jamais exposée)"
            className="input resize-none text-[12px] [font-family:var(--font-mono)]"
            value={form.private_key}
            onChange={e => setForm(p => ({ ...p, private_key: e.target.value }))}
          />

          {err && <p className="field-error m-0">{err}</p>}
          <Button
            size="sm" block
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending || !form.slug || !form.label || !form.public_part || !form.private_key}
          >
            {createMut.isPending ? <CircleNotch size={14} weight="duotone" className="animate-spin" /> : 'Enregistrer'}
          </Button>
        </div>
      )}

      <CertList certs={certs} onDelete={slug => delMut.mutate(slug)} />
    </div>
  )
}

function CertList({ certs, onDelete }: { certs: RemoteCertificateOut[]; onDelete: (slug: string) => void }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  function copyPub(slug: string, pub: string) {
    void navigator.clipboard.writeText(pub).then(() => {
      setCopied(slug); setTimeout(() => setCopied(null), 2000)
    })
  }

  if (certs.length === 0) {
    return (
      <div className="border-y border-[var(--color-divider)]">
        <EmptyState className="py-10" message="Aucun certificat enregistré." />
      </div>
    )
  }

  return (
    <div className="divide-y divide-[var(--color-divider)] border-y border-[var(--color-divider)]">
      {certs.map((c: RemoteCertificateOut) => (
        <div key={c.id}>
          <div className="flex items-center gap-3 py-3">
            <Key size={16} weight="duotone" className="shrink-0 text-ink/[0.45]" />
            <div className="min-w-0 flex-1">
              <p className="m-0 text-[15px] font-[600] [font-family:var(--font-heading)]">
                {c.label}{' '}
                <span className="text-[12px] font-normal text-ink/[0.45] [font-family:var(--font-mono)]">({c.slug})</span>
              </p>
              <p className="m-0 text-[12px] text-ink/[0.55]">
                {c.cert_type === 'ssh_key' ? 'Clé SSH' : 'Certificat TLS'}
                {c.fingerprint ? ` · ${c.fingerprint}` : ''}
              </p>
            </div>
            {c.expires_at && <span className="tag tag-accent-2">{new Date(c.expires_at).toLocaleDateString()}</span>}
            <button
              type="button"
              onClick={() => setExpanded(e => e === c.slug ? null : c.slug)}
              className="cursor-pointer border-0 bg-transparent px-2 py-1 text-accent-700 hover:text-accent-800"
              title={expanded === c.slug ? 'Masquer la clé publique' : 'Afficher la clé publique'}
            >
              {expanded === c.slug ? <CaretDown size={16} weight="duotone" /> : <CaretRight size={16} weight="duotone" />}
            </button>
            <button
              type="button"
              onClick={() => onDelete(c.slug)}
              className="cursor-pointer border-0 bg-transparent p-1 text-ink/[0.35] hover:text-accent-2-700"
            >
              <Trash size={16} weight="duotone" />
            </button>
          </div>
          {expanded === c.slug && (
            <div className="mb-3 rounded-md bg-surface px-4 py-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="m-0 text-[12px] font-[600] text-ink/[0.65]">
                  {c.cert_type === 'ssh_key' ? 'Clé publique — à ajouter comme deploy key sur GitHub / GitLab' : 'Certificat PEM (partie publique)'}
                </p>
                <button
                  type="button"
                  onClick={() => copyPub(c.slug, c.public_part)}
                  className="flex cursor-pointer items-center gap-1 rounded-md border border-[var(--color-divider)] bg-paper px-2 py-1 text-[11px] text-accent-700 hover:text-accent-800"
                >
                  <Copy size={12} weight="duotone" />
                  {copied === c.slug ? 'Copié !' : 'Copier'}
                </button>
              </div>
              <pre className="m-0 rounded-md bg-paper px-3 py-2 text-[12px] whitespace-pre-wrap break-all select-all text-ink/[0.75] [font-family:var(--font-mono)]">
                {c.public_part}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Formulaire Remote Point (création / édition)
// ─────────────────────────────────────────────────────────────────────────────

const PROVIDERS: { value: GitProvider; label: string }[] = [
  { value: 'github', label: 'GitHub' },
  { value: 'gitlab', label: 'GitLab' },
  { value: 'gitea', label: 'Gitea' },
  { value: 'custom', label: 'Personnalisé' },
]

const GIT_PROVIDER_HOST: Record<GitProvider, string> = {
  github: 'github.com',
  gitlab: 'gitlab.com',
  gitea: '',
  custom: '',
}

function PointForm({ initial, onSave, onCancel, certs, submitting = false }: {
  initial?: RemotePointOut
  onSave: (body: RemotePointBody & { slug?: string }) => void
  onCancel: () => void
  certs: RemoteCertificateOut[]
  submitting?: boolean
}) {
  const isEdit = !!initial
  const [form, setForm] = useState<RemotePointBody & { slug: string }>({
    slug: initial?.slug ?? '',
    label: initial?.label ?? '',
    point_type: initial?.point_type ?? 'git',
    host: initial?.host ?? '',
    port: initial?.port ?? null,
    username: initial?.username ?? '',
    git_provider: initial?.git_provider ?? null,
    git_repo: initial?.git_repo ?? null,
    git_branch: initial?.git_branch ?? 'main',
    auth_type: initial?.auth_type ?? 'pat',
    auth_storage: initial?.auth_storage ?? 'vault',
    auth_secret: null,
    auth_vault_ref: initial?.auth_vault_ref ?? null,
    certificate_slug: initial?.certificate_slug ?? null,
  })

  const isGit = form.point_type === 'git'

  function setProvider(p: GitProvider) {
    const h = GIT_PROVIDER_HOST[p]
    setForm(f => ({ ...f, git_provider: p, host: h || f.host }))
  }

  return (
    <div className="flex flex-col gap-3 border-y border-[var(--color-divider)] py-4">
      <div className="grid grid-cols-2 gap-3">
        <Input
          placeholder="Label"
          value={form.label}
          onChange={e => { const v = e.target.value; setForm(p => ({ ...p, label: v, ...(!isEdit ? { slug: slugify(v) } : {}) })) }}
          className={isEdit ? 'col-span-2' : ''}
        />
        {!isEdit && <Input placeholder="slug (auto)" value={form.slug} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Type">
          <select className="input" value={form.point_type} onChange={e => setForm(p => ({ ...p, point_type: e.target.value as PointType, auth_type: e.target.value === 'git' ? 'pat' : 'password' }))}>
            <option value="git">Git</option>
            <option value="sftp">SFTP</option>
            <option value="ftp">FTP</option>
            <option value="ftps">FTPS</option>
          </select>
        </Field>
        {isGit ? (
          <Field label="Hébergeur">
            <select className="input" value={form.git_provider ?? ''} onChange={e => setProvider(e.target.value as GitProvider)}>
              <option value="">-- choisir --</option>
              {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </Field>
        ) : (
          <Input placeholder="Port (optionnel)" type="number" value={form.port ?? ''} onChange={e => setForm(p => ({ ...p, port: e.target.value ? Number(e.target.value) : null }))} />
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label={isGit ? "Hôte git (serveur, pas l'URL du repo)" : 'Hôte (IP ou nom DNS)'}>
          <Input placeholder={isGit ? 'github.com' : '192.168.1.10'} value={form.host} onChange={e => setForm(p => ({ ...p, host: e.target.value }))} />
        </Field>
        <Field label={isGit ? 'Utilisateur SSH (git chez GitHub/GitLab)' : 'Utilisateur'}>
          <Input placeholder={isGit ? 'git' : 'root'} value={form.username} onChange={e => setForm(p => ({ ...p, username: e.target.value }))} />
        </Field>
      </div>

      {isGit && (
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Dépôt — organisation/nom"
            hint="L'identifiant du dépôt chez l'hébergeur, pas un chemin (une URL collée est réduite automatiquement). Le sous-répertoire de destination se choisit sur le job de sauvegarde."
          >
            <Input placeholder="ag-flow/backup-docflow" value={form.git_repo ?? ''} onChange={e => setForm(p => ({ ...p, git_repo: e.target.value }))} />
          </Field>
          <Field label="Branche">
            <Input placeholder="main" value={form.git_branch ?? 'main'} onChange={e => setForm(p => ({ ...p, git_branch: e.target.value }))} />
          </Field>
        </div>
      )}

      <Field label="Authentification">
        <div className="flex gap-2">
          <select className="input flex-1" value={form.auth_type} onChange={e => setForm(p => ({ ...p, auth_type: e.target.value as 'password' | 'pat' | 'certificate', auth_storage: e.target.value !== 'certificate' ? p.auth_storage : null }))}>
            {isGit ? (
              <>
                <option value="pat">PAT (Personal Access Token)</option>
                <option value="certificate">Clé SSH</option>
              </>
            ) : (
              <>
                <option value="password">Mot de passe</option>
                <option value="certificate">Certificat</option>
              </>
            )}
          </select>
          {form.auth_type !== 'certificate' && (
            <select className="input flex-1" value={form.auth_storage ?? 'vault'} onChange={e => setForm(p => ({ ...p, auth_storage: e.target.value as 'local' | 'vault' }))}>
              <option value="vault">Dans le vault</option>
              <option value="local">En local (chiffré)</option>
            </select>
          )}
        </div>
      </Field>

      {form.auth_type === 'certificate' && (
        <Field label="Certificat">
          <select className="input" value={form.certificate_slug ?? ''} onChange={e => setForm(p => ({ ...p, certificate_slug: e.target.value || null }))}>
            <option value="">-- choisir --</option>
            {certs.filter(c => isGit ? c.cert_type === 'ssh_key' : true).map(c => <option key={c.slug} value={c.slug}>{c.label} ({c.slug})</option>)}
          </select>
        </Field>
      )}
      {form.auth_type !== 'certificate' && form.auth_storage === 'vault' && (
        <Input placeholder="${vault://wallet-name:/chemin/secret}" value={form.auth_vault_ref ?? ''} onChange={e => setForm(p => ({ ...p, auth_vault_ref: e.target.value || null }))} />
      )}
      {form.auth_type !== 'certificate' && form.auth_storage === 'local' && (
        <Input type="password" placeholder={isEdit ? 'Laisser vide pour conserver le secret existant' : 'Secret (chiffré en base)'} value={form.auth_secret ?? ''} onChange={e => setForm(p => ({ ...p, auth_secret: e.target.value || null }))} />
      )}

      {isEdit && (
        <div className="flex items-center gap-2 pt-1">
          <TestConnectionButton slug={initial!.slug} />
          <span className="text-[12px] text-ink/[0.5]">
            teste la configuration enregistrée — enregistrez d'abord vos modifications
          </span>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <Button
          size="sm"
          className="flex-1"
          onClick={() => {
            if (submitting) return
            const body = { ...form, git_repo: form.git_repo ? normalizeGitRepo(form.git_repo) : form.git_repo }
            if (body.auth_type === 'certificate') {
              // Reliquats du mode password/pat : incohérents avec l'auth par
              // certificat (le CHECK SQL vault↔ref les refuse).
              body.auth_storage = null
              body.auth_secret = null
              body.auth_vault_ref = null
            }
            onSave(body)
          }}
          disabled={submitting}
        >
          Enregistrer
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>Annuler</Button>
      </div>
    </div>
  )
}

/** Champ « Repo » : accepte org/nom, mais aussi une URL https ou SSH collée
 *  telle quelle (https://github.com/org/nom.git, git@github.com:org/nom.git…)
 *  — on n'en retient que org/nom. */
export function normalizeGitRepo(input: string): string {
  const v = input.trim().replace(/\.git$/, '')
  const m = v.match(/^(?:https?:\/\/[^/]+\/|git@[^:]+:|ssh:\/\/(?:git@)?[^/]+\/)(.+)$/)
  return (m ? m[1] : v).replace(/^\/+|\/+$/g, '')
}

// ─────────────────────────────────────────────────────────────────────────────
// Test de connexion — adapté au type par le backend (git ls-remote / sftp / ftp)
// ─────────────────────────────────────────────────────────────────────────────

function TestConnectionButton({ slug, compact = false }: { slug: string; compact?: boolean }) {
  const testMut = useMutation({ mutationFn: () => remotePointsApi.test(slug) })
  const detailClass = compact ? 'max-w-[260px] truncate' : ''
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Button
        size="sm"
        variant="secondary"
        onClick={() => testMut.mutate()}
        disabled={testMut.isPending}
        data-testid={`test-point-${slug}`}
      >
        {testMut.isPending
          ? <CircleNotch size={14} weight="duotone" className="animate-spin" />
          : <Plug size={14} weight="duotone" />}
        {compact ? 'Tester' : 'Tester la connexion'}
      </Button>
      {testMut.data && (
        <span
          className={`flex items-center gap-1 text-[12px] ${testMut.data.ok ? 'text-accent-700' : 'text-accent-2-700'}`}
          title={testMut.data.detail}
          data-testid="test-connection-result"
        >
          {testMut.data.ok ? <CheckCircle size={14} weight="duotone" className="shrink-0" /> : <XCircle size={14} weight="duotone" className="shrink-0" />}
          <span className={detailClass}>{testMut.data.detail}</span>
        </span>
      )}
      {testMut.isError && (
        <span
          className="flex items-center gap-1 text-[12px] text-accent-2-700"
          title={(testMut.error as Error).message}
          data-testid="test-connection-result"
        >
          <XCircle size={14} weight="duotone" className="shrink-0" />
          <span className={detailClass}>{(testMut.error as Error).message}</span>
        </span>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// URL de connexion calculée depuis un RemotePointOut
// ─────────────────────────────────────────────────────────────────────────────

function connectionUrl(pt: RemotePointOut): string {
  if (pt.point_type === 'git') {
    const host = pt.host
    const repo = pt.git_repo ?? ''
    if (pt.auth_type === 'certificate') {
      return `git@${host}:${repo}.git`
    }
    return `https://${host}/${repo}.git`
  }
  const portSuffix = pt.port ? `:${pt.port}` : ''
  return `${pt.point_type}://${pt.username}@${pt.host}${portSuffix}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Remote Points
// ─────────────────────────────────────────────────────────────────────────────

const TYPE_ICON: Record<PointType, React.ReactNode> = {
  git: <GitBranch size={16} weight="duotone" className="text-accent-700" />,
  sftp: <Network size={16} weight="duotone" className="text-ink/[0.55]" />,
  ftp: <Globe size={16} weight="duotone" className="text-ink/[0.45]" />,
  ftps: <ShieldCheck size={16} weight="duotone" className="text-ink/[0.55]" />,
}

function CopyableUrl({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    void navigator.clipboard.writeText(url).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <div className="mt-1 flex items-center gap-1.5">
      <code className="flex-1 truncate rounded-sm bg-surface px-2 py-0.5 text-[12px] text-ink/[0.7] [font-family:var(--font-mono)]">{url}</code>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 cursor-pointer border-0 bg-transparent p-0 text-ink/[0.4] hover:text-ink"
        title="Copier l'URL"
      >
        {copied ? <CheckCircle size={14} weight="duotone" className="text-accent-700" /> : <Copy size={14} weight="duotone" />}
      </button>
    </div>
  )
}

function RemotePointsTab() {
  const qc = useQueryClient()
  const { data: points = [] } = useQuery({ queryKey: ['remote-points'], queryFn: remotePointsApi.list })
  const { data: certs = [] } = useQuery({ queryKey: ['remote-certs'], queryFn: remoteCertsApi.list })
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: (body: RemotePointBody & { slug: string }) => remotePointsApi.create(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['remote-points'] }); setCreating(false) },
    onError: (e) => setErr((e as Error).message),
  })
  const updateMut = useMutation({
    mutationFn: ({ slug, body }: { slug: string; body: RemotePointBody }) => {
      // slug immuable : le backend (extra=forbid) rejette sa présence dans le corps
      const { slug: _immutable, ...rest } = body
      return remotePointsApi.update(slug, rest)
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['remote-points'] }); setEditing(null) },
    onError: (e) => setErr((e as Error).message),
  })
  const delMut = useMutation({
    mutationFn: (slug: string) => remotePointsApi.delete(slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['remote-points'] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="m-0 text-[13px] text-ink/[0.55]">{points.length} point{points.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => { setCreating(v => !v); setErr(null) }}>
          <Plus size={14} weight="duotone" />{creating ? 'Annuler' : 'Ajouter'}
        </Button>
      </div>

      <div aria-live="polite" className="empty:hidden">
        {err && <p className="m-0 text-[13px] text-accent-2-700">{err}</p>}
      </div>

      {creating && (
        <PointForm
          certs={certs}
          onSave={(body) => createMut.mutate(body as RemotePointBody & { slug: string })}
          onCancel={() => setCreating(false)}
          submitting={createMut.isPending}
        />
      )}

      {points.length === 0 && !creating ? (
        <div className="border-y border-[var(--color-divider)]">
          <EmptyState className="py-10" message="Aucun remote point." />
        </div>
      ) : (
        <div className="divide-y divide-[var(--color-divider)] border-y border-[var(--color-divider)]">
          {(points as RemotePointOut[]).map(pt => (
            <div key={pt.id}>
              <div className="flex items-center gap-3 py-3">
                <div className="shrink-0">{TYPE_ICON[pt.point_type]}</div>
                <div className="min-w-0 flex-1">
                  <p className="m-0 text-[15px] font-[600] [font-family:var(--font-heading)]">
                    {pt.label}{' '}
                    <span className="text-[12px] font-normal text-ink/[0.45] [font-family:var(--font-mono)]">({pt.slug})</span>
                  </p>
                  <p className="m-0 text-[12px] text-ink/[0.55]">
                    {pt.point_type.toUpperCase()}
                    {' · '}{pt.auth_type === 'certificate' ? `clé SSH: ${pt.certificate_slug}` : pt.auth_storage === 'vault' ? 'vault' : 'local'}
                  </p>
                  <CopyableUrl url={connectionUrl(pt)} />
                </div>
                <div className="flex items-center gap-1">
                  <TestConnectionButton slug={pt.slug} compact />
                  <button
                    type="button"
                    onClick={() => setEditing(e => e === pt.slug ? null : pt.slug)}
                    className="cursor-pointer border-0 bg-transparent px-2 py-1 text-[13px] text-accent-700 hover:underline"
                    data-testid={`edit-point-${pt.slug}`}
                  >
                    Éditer
                  </button>
                  <button
                    type="button"
                    onClick={() => delMut.mutate(pt.slug)}
                    className="cursor-pointer border-0 bg-transparent p-1 text-ink/[0.35] hover:text-accent-2-700"
                  >
                    <Trash size={16} weight="duotone" />
                  </button>
                </div>
              </div>
              {editing === pt.slug && (
                <div className="pb-4">
                  <PointForm
                    initial={pt}
                    certs={certs}
                    onSave={(body) => updateMut.mutate({ slug: pt.slug, body })}
                    onCancel={() => setEditing(null)}
                    submitting={updateMut.isPending}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Sauvegarde
// ─────────────────────────────────────────────────────────────────────────────

function RunStatus({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle size={16} weight="duotone" className="text-accent-700" />
  if (status === 'error') return <XCircle size={16} weight="duotone" className="text-accent-2-700" />
  return <CircleNotch size={16} weight="duotone" className="animate-spin text-accent-700" />
}

function JobCard({ job, onEdit }: { job: BackupJobOut; onEdit: () => void }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const { data: runs = [], refetch } = useQuery({
    queryKey: ['backup-runs', job.slug],
    queryFn: () => backupApi.listRuns(job.slug),
    enabled: expanded,
    // Un run tourne en tâche de fond : rafraîchir jusqu'à son état final,
    // sinon « en cours… » reste affiché indéfiniment.
    refetchInterval: (query) => {
      const data = query.state.data as BackupJobRunOut[] | undefined
      return data?.some((r) => r.status === 'running') ? 2000 : false
    },
  })
  const hasRunning = (runs as BackupJobRunOut[]).some((r) => r.status === 'running')
  const wasRunning = useRef(false)
  useEffect(() => {
    // À la fin d'un run (running → terminé), recharger la liste des jobs
    // pour rafraîchir last_run_status.
    if (wasRunning.current && !hasRunning) {
      void qc.invalidateQueries({ queryKey: ['backup-jobs'] })
    }
    wasRunning.current = hasRunning
  }, [hasRunning, qc])

  const delMut = useMutation({
    mutationFn: () => backupApi.deleteJob(job.slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['backup-jobs'] }),
  })
  const toggleMut = useMutation({
    mutationFn: () => backupApi.updateJob(job.slug, {
      label: job.label, enabled: !job.enabled,
      remote_point_slug: job.remote_point_slug, workspace_slug: job.workspace_slug,
      schedule_cron: job.schedule_cron, schedule_every_seconds: job.schedule_every_seconds,
      git_base_path: job.git_base_path, include_restore_env: job.include_restore_env,
      retention_count: job.retention_count,
    }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['backup-jobs'] }),
  })
  const runMut = useMutation({
    mutationFn: () => backupApi.runJob(job.slug),
    onSuccess: () => {
      // Le run tourne en tâche de fond (202) : déplier l'historique pour le suivre.
      setExpanded(true)
      void refetch()
      void qc.invalidateQueries({ queryKey: ['backup-jobs'] })
    },
  })

  return (
    <div>
      <div className="flex items-center gap-3 py-3">
        {job.strategy === 'git_sync'
          ? <GitBranch size={16} weight="duotone" className="shrink-0 text-accent-700" />
          : <HardDrive size={16} weight="duotone" className="shrink-0 text-ink/[0.55]" />}
        <div className="min-w-0 flex-1">
          <p className="m-0 text-[15px] font-[600] [font-family:var(--font-heading)]">
            {job.label}{' '}
            <span className="text-[12px] font-normal text-ink/[0.45] [font-family:var(--font-mono)]">({job.slug})</span>
          </p>
          <p className="m-0 text-[12px] text-ink/[0.55]">
            {job.strategy} · {job.remote_point_slug}
            {job.workspace_slug ? ` · ws:${job.workspace_slug}` : ' · toute instance'}
            {' · '}{describeSchedule(job.schedule_cron, job.schedule_every_seconds)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {job.last_run_status && <RunStatus status={job.last_run_status} />}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => runMut.mutate()}
            disabled={runMut.isPending}
            title="Déclencher un run immédiat, hors planification"
            data-testid={`run-job-${job.slug}`}
          >
            {runMut.isPending
              ? <CircleNotch size={12} weight="duotone" className="animate-spin" />
              : <Play size={12} weight="duotone" />}
            Lancer
          </Button>
          <button
            type="button"
            onClick={() => toggleMut.mutate()}
            className={`cursor-pointer border-0 ${job.enabled ? 'tag tag-accent' : 'tag tag-neutral'}`}
          >
            {job.enabled ? 'Actif' : 'Inactif'}
          </button>
          <button
            type="button"
            onClick={onEdit}
            className="cursor-pointer border-0 bg-transparent px-1 text-[13px] text-accent-700 hover:underline"
            data-testid={`edit-job-${job.slug}`}
          >
            Éditer
          </button>
          <button
            type="button"
            onClick={() => { setExpanded(v => !v); if (!expanded) void refetch() }}
            className="cursor-pointer border-0 bg-transparent p-1 text-ink/[0.4] hover:text-ink"
          >
            {expanded ? <CaretDown size={16} weight="duotone" /> : <CaretRight size={16} weight="duotone" />}
          </button>
          <button
            type="button"
            onClick={() => delMut.mutate()}
            className="cursor-pointer border-0 bg-transparent p-0.5 text-ink/[0.35] hover:text-accent-2-700"
          >
            <Trash size={16} weight="duotone" />
          </button>
        </div>
      </div>

      {runMut.isError && (
        <p className="m-0 pb-2 text-[12px] text-accent-2-700" data-testid={`run-job-error-${job.slug}`}>
          {(runMut.error as Error).message}
        </p>
      )}

      {expanded && (
        <div className="mb-3 rounded-md bg-surface px-4 py-3">
          <p className="m-0 mb-2 text-[11px] font-[600] uppercase tracking-[0.08em] text-ink/[0.5]">Historique des runs</p>
          {(runs as BackupJobRunOut[]).length === 0 && <p className="m-0 text-[12px] text-ink/[0.5]">Aucun run enregistré.</p>}
          <div className="space-y-1">
            {(runs as BackupJobRunOut[]).map((r: BackupJobRunOut) => (
              <div key={r.id} className="flex items-center gap-2 text-[12px]">
                <RunStatus status={r.status} />
                <span className="text-ink/[0.55]">{new Date(r.started_at).toLocaleString()}</span>
                {r.status === 'success' && (
                  <span className="text-ink/[0.75]">
                    {r.files_written ?? 0} écrits · {r.files_deleted ?? 0} supprimés
                    {r.commit_sha ? ` · ${r.commit_sha}` : ' · rien à committer'}
                  </span>
                )}
                {r.status === 'error' && <span className="truncate text-accent-2-700">{r.error_message}</span>}
                {r.status === 'running' && <span className="text-accent-700">en cours…</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

type ScheduleMode = 'interval' | 'daily' | 'hourly'

/** Cron minute/heure fixes → mode + heure "HH:MM" pour l'input time ; sinon `null`. */
function cronToDailyTime(cron: string): string | null {
  const m = /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec(cron)
  if (!m) return null
  const minute = Number(m[1])
  const hour = Number(m[2])
  if (minute > 59 || hour > 23) return null
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function dailyTimeToCron(time: string): string {
  const [hour, minute] = time.split(':').map(Number)
  return `${minute} ${hour} * * *`
}

/** Résumé lisible d'une planification pour l'affichage — retombe sur le cron brut si non reconnu. */
function describeSchedule(cron: string | null, everySeconds: number | null): string {
  if (cron === '0 * * * *') return 'toutes les heures'
  if (cron) {
    const time = cronToDailyTime(cron)
    return time ? `tous les jours à ${time}` : `cron: ${cron}`
  }
  return `toutes les ${everySeconds}s`
}

function BackupTab() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useQuery({ queryKey: ['backup-jobs'], queryFn: backupApi.listJobs, refetchInterval: 15000 })
  const { data: points = [] } = useQuery({ queryKey: ['remote-points'], queryFn: remotePointsApi.list })
  const [showForm, setShowForm] = useState(false)
  const [editingSlug, setEditingSlug] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const emptyForm: BackupJobBody & { slug: string } = {
    slug: '', label: '', strategy: 'git_sync', enabled: true,
    remote_point_slug: '', workspace_slug: null,
    schedule_cron: null, schedule_every_seconds: 3600,
    git_base_path: null, include_restore_env: false, retention_count: null,
  }
  const [form, setForm] = useState<BackupJobBody & { slug: string }>(emptyForm)
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>('daily')
  const [dailyTime, setDailyTime] = useState('03:00')

  function startEdit(job: BackupJobOut) {
    setErr(null)
    setEditingSlug(job.slug)
    setForm({
      slug: job.slug, label: job.label, strategy: job.strategy, enabled: job.enabled,
      remote_point_slug: job.remote_point_slug, workspace_slug: job.workspace_slug,
      schedule_cron: job.schedule_cron, schedule_every_seconds: job.schedule_every_seconds,
      git_base_path: job.git_base_path, include_restore_env: job.include_restore_env,
      retention_count: job.retention_count,
    })
    // Retrouver le mode de planification depuis les valeurs enregistrées
    if (job.schedule_cron === '0 * * * *') {
      setScheduleMode('hourly')
    } else if (job.schedule_cron) {
      setScheduleMode('daily')
      const time = cronToDailyTime(job.schedule_cron)
      if (time) setDailyTime(time)
    } else {
      setScheduleMode('interval')
    }
    setShowForm(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const schedule = scheduleMode === 'interval'
        ? { schedule_cron: null, schedule_every_seconds: form.schedule_every_seconds }
        : scheduleMode === 'daily'
          ? { schedule_cron: dailyTimeToCron(dailyTime), schedule_every_seconds: null }
          : { schedule_cron: '0 * * * *', schedule_every_seconds: null }
      // slug et stratégie immuables : jamais dans le corps d'un update
      // (le backend, extra=forbid, les rejette)
      const { slug, strategy, ...rest } = { ...form, ...schedule }
      return editingSlug
        ? backupApi.updateJob(editingSlug, rest)
        : backupApi.createJob({ ...rest, strategy, slug })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['backup-jobs'] })
      setShowForm(false)
      setEditingSlug(null)
    },
    onError: (e) => setErr((e as Error).message),
  })

  const gitPoints = (points as RemotePointOut[]).filter(p => p.point_type === 'git')
  const dumpPoints = (points as RemotePointOut[]).filter(p => ['ftp', 'ftps', 'sftp'].includes(p.point_type))
  const availablePoints = form.strategy === 'git_sync' ? gitPoints : dumpPoints

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="m-0 text-[13px] text-ink/[0.55]">{(jobs as BackupJobOut[]).length} job{(jobs as BackupJobOut[]).length !== 1 ? 's' : ''}</p>
        <Button
          size="sm"
          onClick={() => {
            setErr(null)
            if (showForm) {
              setShowForm(false)
              setEditingSlug(null)
            } else {
              setEditingSlug(null)
              setForm(emptyForm)
              setScheduleMode('daily')
              setDailyTime('03:00')
              setShowForm(true)
            }
          }}
        >
          <Plus size={14} weight="duotone" />{showForm ? 'Annuler' : 'Nouveau job'}
        </Button>
      </div>

      {showForm && (
        <div className="flex flex-col gap-3 border-y border-[var(--color-divider)] py-4">
          <div className="grid grid-cols-2 gap-3">
            <Input placeholder="Label" value={form.label} onChange={e => { const v = e.target.value; setForm(p => ({ ...p, label: v, ...(editingSlug ? {} : { slug: slugify(v) }) })) }} />
            <Input placeholder="slug (auto)" value={form.slug} disabled={editingSlug !== null} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Stratégie">
              <select className="input" disabled={editingSlug !== null} value={form.strategy} onChange={e => setForm(p => ({ ...p, strategy: e.target.value as 'git_sync' | 'db_dump', remote_point_slug: '' }))}>
                <option value="git_sync">Sync git (documents)</option>
                <option value="db_dump">Dump DB (pg_dump)</option>
              </select>
            </Field>
            <Field label="Remote point">
              <select className="input" value={form.remote_point_slug} onChange={e => setForm(p => ({ ...p, remote_point_slug: e.target.value }))}>
                <option value="">-- choisir --</option>
                {availablePoints.map((p: RemotePointOut) => <option key={p.slug} value={p.slug}>{p.label}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Workspace (vide = toute l'instance)">
            <Input placeholder="mon-workspace" value={form.workspace_slug ?? ''} onChange={e => setForm(p => ({ ...p, workspace_slug: e.target.value || null }))} />
          </Field>
          <Field
            label={form.strategy === 'git_sync'
              ? 'Sous-répertoire de destination dans le repo (optionnel)'
              : 'Répertoire de destination sur le serveur (optionnel, créé si absent)'}
          >
            <Input placeholder={form.strategy === 'git_sync' ? 'backup/docflow' : '/backups/docflow'} value={form.git_base_path ?? ''} onChange={e => setForm(p => ({ ...p, git_base_path: e.target.value || null }))} />
          </Field>
          {form.strategy === 'db_dump' && (
            <label className="flex items-start gap-2 text-[14px] text-ink/[0.85]">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={form.include_restore_env ?? false}
                onChange={e => setForm(p => ({ ...p, include_restore_env: e.target.checked }))}
                data-testid="include-restore-env"
              />
              <span>
                Déposer le matériel de restauration à côté de chaque archive
                (<span className="text-[12px] [font-family:var(--font-mono)]">&lt;dump&gt;.key</span> : clé de chiffrement,
                JWT_SECRET, DATABASE_URL). À réserver à un serveur de backup de confiance.
              </span>
            </label>
          )}
          {form.strategy === 'db_dump' && (
            <Field label="Nombre de dumps à conserver sur le serveur (vide = tout garder)">
              <Input
                type="number"
                min={1}
                placeholder="ex. 7 — les archives plus anciennes (et leur .key) sont supprimées après chaque run"
                value={form.retention_count ?? ''}
                onChange={e => setForm(p => ({ ...p, retention_count: e.target.value ? Number(e.target.value) : null }))}
                data-testid="retention-count"
              />
            </Field>
          )}
          <Field label="Planification">
            <div className="flex gap-2">
              <select
                className="input flex-1"
                value={scheduleMode}
                onChange={e => setScheduleMode(e.target.value as ScheduleMode)}
                data-testid="schedule-mode-select"
              >
                <option value="daily">Quotidien (heure de démarrage)</option>
                <option value="hourly">Toutes les heures</option>
                <option value="interval">Intervalle (secondes)</option>
              </select>
              {scheduleMode === 'interval' && (
                <Input
                  type="number"
                  placeholder="3600"
                  className="flex-1"
                  value={form.schedule_every_seconds ?? ''}
                  onChange={e => setForm(p => ({ ...p, schedule_every_seconds: Number(e.target.value) || null }))}
                />
              )}
              {scheduleMode === 'daily' && (
                <Input
                  type="time"
                  className="flex-1"
                  value={dailyTime}
                  onChange={e => setDailyTime(e.target.value)}
                  data-testid="schedule-daily-time"
                />
              )}
              {scheduleMode === 'hourly' && (
                <p className="m-0 flex items-center text-[12px] text-ink/[0.55]">S'exécute au début de chaque heure (HH:00).</p>
              )}
            </div>
          </Field>
          {err && <p className="field-error m-0">{err}</p>}
          <Button
            size="sm" block
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending || !form.slug || !form.label || !form.remote_point_slug}
            data-testid="save-job-btn"
          >
            {saveMut.isPending
              ? <CircleNotch size={14} weight="duotone" className="animate-spin" />
              : editingSlug ? 'Enregistrer' : 'Créer le job'}
          </Button>
        </div>
      )}

      {(jobs as BackupJobOut[]).length === 0 && !showForm ? (
        <div className="border-y border-[var(--color-divider)]">
          <EmptyState className="py-10" message="Aucun job de sauvegarde configuré." />
        </div>
      ) : (
        <div className="divide-y divide-[var(--color-divider)] border-y border-[var(--color-divider)]">
          {(jobs as BackupJobOut[]).map((j: BackupJobOut) => (
            <JobCard key={j.id} job={j} onEdit={() => startEdit(j)} />
          ))}
        </div>
      )}

      <RestoreGitPanel gitPoints={gitPoints} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Restauration depuis le miroir git — réalimente l'instance (additif)
// ─────────────────────────────────────────────────────────────────────────────

function RestoreGitPanel({ gitPoints }: { gitPoints: RemotePointOut[] }) {
  const qc = useQueryClient()
  const [pointSlug, setPointSlug] = useState('')
  const [basePath, setBasePath] = useState('')
  const [workspace, setWorkspace] = useState('')

  const restoreMut = useMutation({
    mutationFn: () => backupApi.restoreGit({
      remote_point_slug: pointSlug,
      git_base_path: basePath.trim() || null,
      workspace: workspace.trim() || null,
    }),
    onSuccess: () => void qc.invalidateQueries(),
  })
  const report = restoreMut.data

  return (
    <div className="mt-12 space-y-3 border-t border-[var(--color-divider)] pt-5">
      <div>
        <p className="m-0 text-[15px] font-[600] [font-family:var(--font-heading)]">Restauration depuis le miroir git</p>
        <p className="m-0 mt-1 text-[12px] text-ink/[0.55]">
          Clone le dépôt de sauvegarde du remote point et recrée workspaces, types, blocs et
          documents. <span className="font-[600]">Additif et rejouable</span> : crée ce qui manque,
          réaligne les documents existants, ne supprime jamais rien.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Remote point git">
          <select
            className="input"
            value={pointSlug}
            onChange={e => setPointSlug(e.target.value)}
            data-testid="restore-git-point"
          >
            <option value="">-- choisir --</option>
            {gitPoints.map(p => <option key={p.slug} value={p.slug}>{p.label}</option>)}
          </select>
        </Field>
        <Field label="Sous-répertoire (vide = détection automatique)">
          <Input placeholder="auto — détecté depuis la sauvegarde" value={basePath} onChange={e => setBasePath(e.target.value)} />
        </Field>
        <Field label="Workspace seul (optionnel)">
          <Input placeholder="vide = tous" value={workspace} onChange={e => setWorkspace(e.target.value)} />
        </Field>
      </div>
      <Button
        size="sm"
        onClick={() => restoreMut.mutate()}
        disabled={!pointSlug || restoreMut.isPending}
        data-testid="restore-git-btn"
      >
        {restoreMut.isPending
          ? <><CircleNotch size={14} weight="duotone" className="animate-spin" />Restauration en cours…</>
          : 'Restaurer'}
      </Button>
      {restoreMut.isError && (
        <p className="m-0 text-[12px] text-accent-2-700">{(restoreMut.error as Error).message}</p>
      )}
      {report && (
        <div className="space-y-1 rounded-md bg-surface px-3 py-2 text-[12px] text-ink/[0.75]" data-testid="restore-git-report">
          <p className="m-0">
            {report.workspaces_created} workspace(s) créé(s) · {report.blocks_created} bloc(s) ·
            {' '}{report.types_imported} import(s) de types · {report.docs_created} document(s) créé(s) ·
            {' '}{report.docs_updated} réaligné(s)
          </p>
          {report.errors.length > 0 && (
            <ul className="m-0 list-disc pl-4 text-accent-2-700">
              {report.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Page principale
// ─────────────────────────────────────────────────────────────────────────────

type Tab = 'points' | 'certificates' | 'backup'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'certificates', label: 'Certificats', icon: <Key size={15} weight="duotone" /> },
  { id: 'points', label: 'Remote Points', icon: <Cpu size={15} weight="duotone" /> },
  { id: 'backup', label: 'Sauvegarde', icon: <Clock size={15} weight="duotone" /> },
]

export function RemotePage() {
  const [tab, setTab] = useState<Tab>('certificates')

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title="Connexions & Sauvegarde" />
      <p className="mb-8 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        Certificats, points de connexion distants (git, SFTP, FTP, FTPS) et jobs de
        sauvegarde qui s'y adossent — synchronisation git des documents ou dumps de la
        base, avec restauration depuis le miroir git.
      </p>

      <div className="seg mb-8">
        {TABS.map(t => (
          <label key={t.id} className="seg-opt">
            <input
              type="radio"
              name="remote-tab"
              checked={tab === t.id}
              onChange={() => setTab(t.id)}
            />
            {t.icon}{t.label}
          </label>
        ))}
      </div>

      {tab === 'points' && <RemotePointsTab />}
      {tab === 'certificates' && <CertificatesTab />}
      {tab === 'backup' && <BackupTab />}
    </div>
  )
}
