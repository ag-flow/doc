import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle, ChevronDown, ChevronRight, Clock, Cpu, GitBranch,
  Globe, HardDrive, KeyRound, Loader2, Network, Plus, ShieldCheck,
  Trash2, XCircle,
} from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import {
  type BackupJobBody, type BackupJobOut, type BackupJobRunOut,
  type GitProvider, type PointType, type RemoteCertificateOut,
  type RemotePointBody, type RemotePointOut,
  backupApi, remoteCertsApi, remotePointsApi,
} from '../lib/api'

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Certificats
// ─────────────────────────────────────────────────────────────────────────────

function CertificatesTab() {
  const qc = useQueryClient()
  const { data: certs = [] } = useQuery({ queryKey: ['remote-certs'], queryFn: remoteCertsApi.list })
  const [showForm, setShowForm] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [form, setForm] = useState({ slug: '', label: '', cert_type: 'ssh_key' as 'ssh_key' | 'tls', public_part: '', private_key: '' })

  const createMut = useMutation({
    mutationFn: () => remoteCertsApi.create(form),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['remote-certs'] }); setShowForm(false); setForm({ slug: '', label: '', cert_type: 'ssh_key', public_part: '', private_key: '' }) },
    onError: (e) => setErr((e as Error).message),
  })
  const delMut = useMutation({
    mutationFn: (slug: string) => remoteCertsApi.delete(slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['remote-certs'] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{certs.length} certificat{certs.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => { setShowForm(v => !v); setErr(null) }}>
          <Plus className="h-3.5 w-3.5 mr-1" />{showForm ? 'Annuler' : 'Ajouter'}
        </Button>
      </div>

      {showForm && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input placeholder="slug (ex. deploy-key)" value={form.slug} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />
            <Input placeholder="Label" value={form.label} onChange={e => setForm(p => ({ ...p, label: e.target.value }))} />
          </div>
          <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.cert_type} onChange={e => setForm(p => ({ ...p, cert_type: e.target.value as 'ssh_key' | 'tls' }))}>
            <option value="ssh_key">Clé SSH (git / SFTP)</option>
            <option value="tls">Certificat TLS (FTPS)</option>
          </select>
          <textarea rows={4} placeholder="Clé publique / cert PEM" className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-xs font-mono resize-none" value={form.public_part} onChange={e => setForm(p => ({ ...p, public_part: e.target.value }))} />
          <textarea rows={6} placeholder="Clé privée (chiffrée en base, jamais exposée)" className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-xs font-mono resize-none" value={form.private_key} onChange={e => setForm(p => ({ ...p, private_key: e.target.value }))} />
          {err && <p className="text-xs text-red-600">{err}</p>}
          <Button size="sm" className="w-full" onClick={() => createMut.mutate()} disabled={createMut.isPending || !form.slug || !form.label || !form.public_part || !form.private_key}>
            {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Enregistrer'}
          </Button>
        </div>
      )}

      <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
        {certs.length === 0 && <p className="p-4 text-sm text-gray-400">Aucun certificat enregistré.</p>}
        {certs.map((c: RemoteCertificateOut) => (
          <div key={c.id} className="flex items-center gap-3 px-4 py-3">
            <KeyRound className="h-4 w-4 text-gray-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900">{c.label} <span className="text-xs text-gray-400">({c.slug})</span></p>
              <p className="text-xs text-gray-500">{c.cert_type === 'ssh_key' ? 'Clé SSH' : 'Certificat TLS'}{c.fingerprint ? ` · ${c.fingerprint}` : ''}</p>
            </div>
            {c.expires_at && <p className="text-xs text-amber-600">{new Date(c.expires_at).toLocaleDateString()}</p>}
            <button onClick={() => delMut.mutate(c.slug)} className="text-gray-300 hover:text-red-500 transition-colors">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
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

function PointForm({ initial, onSave, onCancel, certs }: {
  initial?: RemotePointOut
  onSave: (body: RemotePointBody & { slug?: string }) => void
  onCancel: () => void
  certs: RemoteCertificateOut[]
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
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {!isEdit && <Input placeholder="slug" value={form.slug} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />}
        <Input placeholder="Label" value={form.label} onChange={e => setForm(p => ({ ...p, label: e.target.value }))} className={isEdit ? 'col-span-2' : ''} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Type</label>
          <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.point_type} onChange={e => setForm(p => ({ ...p, point_type: e.target.value as PointType, auth_type: e.target.value === 'git' ? 'pat' : 'password' }))}>
            <option value="git">Git</option>
            <option value="sftp">SFTP</option>
            <option value="ftp">FTP</option>
            <option value="ftps">FTPS</option>
          </select>
        </div>
        {isGit ? (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Hébergeur</label>
            <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.git_provider ?? ''} onChange={e => setProvider(e.target.value as GitProvider)}>
              <option value="">-- choisir --</option>
              {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
        ) : (
          <Input placeholder="Port (optionnel)" type="number" value={form.port ?? ''} onChange={e => setForm(p => ({ ...p, port: e.target.value ? Number(e.target.value) : null }))} />
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Input placeholder="Host / URL" value={form.host} onChange={e => setForm(p => ({ ...p, host: e.target.value }))} />
        <Input placeholder="Username" value={form.username} onChange={e => setForm(p => ({ ...p, username: e.target.value }))} />
      </div>

      {isGit && (
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="Repo (org/nom)" value={form.git_repo ?? ''} onChange={e => setForm(p => ({ ...p, git_repo: e.target.value }))} />
          <Input placeholder="Branche (défaut: main)" value={form.git_branch ?? 'main'} onChange={e => setForm(p => ({ ...p, git_branch: e.target.value }))} />
        </div>
      )}

      <div>
        <label className="text-xs text-gray-500 mb-1 block">Authentification</label>
        <div className="flex gap-2">
          <select className="flex-1 rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.auth_type} onChange={e => setForm(p => ({ ...p, auth_type: e.target.value as 'password' | 'pat' | 'certificate', auth_storage: e.target.value !== 'certificate' ? p.auth_storage : null }))}>
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
            <select className="flex-1 rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.auth_storage ?? 'vault'} onChange={e => setForm(p => ({ ...p, auth_storage: e.target.value as 'local' | 'vault' }))}>
              <option value="vault">Dans le vault</option>
              <option value="local">En local (chiffré)</option>
            </select>
          )}
        </div>
      </div>

      {form.auth_type === 'certificate' && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Certificat</label>
          <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.certificate_slug ?? ''} onChange={e => setForm(p => ({ ...p, certificate_slug: e.target.value || null }))}>
            <option value="">-- choisir --</option>
            {certs.filter(c => isGit ? c.cert_type === 'ssh_key' : true).map(c => <option key={c.slug} value={c.slug}>{c.label} ({c.slug})</option>)}
          </select>
        </div>
      )}
      {form.auth_type !== 'certificate' && form.auth_storage === 'vault' && (
        <Input placeholder="${vault://wallet-name:/chemin/secret}" value={form.auth_vault_ref ?? ''} onChange={e => setForm(p => ({ ...p, auth_vault_ref: e.target.value || null }))} />
      )}
      {form.auth_type !== 'certificate' && form.auth_storage === 'local' && (
        <Input type="password" placeholder={isEdit ? 'Laisser vide pour conserver le secret existant' : 'Secret (chiffré en base)'} value={form.auth_secret ?? ''} onChange={e => setForm(p => ({ ...p, auth_secret: e.target.value || null }))} />
      )}

      <div className="flex gap-2 pt-1">
        <Button size="sm" className="flex-1" onClick={() => onSave(form)}>Enregistrer</Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>Annuler</Button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Remote Points
// ─────────────────────────────────────────────────────────────────────────────

const TYPE_ICON: Record<PointType, React.ReactNode> = {
  git: <GitBranch className="h-4 w-4 text-indigo-500" />,
  sftp: <Network className="h-4 w-4 text-teal-500" />,
  ftp: <Globe className="h-4 w-4 text-gray-400" />,
  ftps: <ShieldCheck className="h-4 w-4 text-emerald-500" />,
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
    mutationFn: ({ slug, body }: { slug: string; body: RemotePointBody }) => remotePointsApi.update(slug, body),
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
        <p className="text-sm text-gray-500">{points.length} point{points.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => { setCreating(v => !v); setErr(null) }}>
          <Plus className="h-3.5 w-3.5 mr-1" />{creating ? 'Annuler' : 'Ajouter'}
        </Button>
      </div>

      {err && <p className="text-xs text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      {creating && (
        <PointForm
          certs={certs}
          onSave={(body) => createMut.mutate(body as RemotePointBody & { slug: string })}
          onCancel={() => setCreating(false)}
        />
      )}

      <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
        {points.length === 0 && !creating && <p className="p-4 text-sm text-gray-400">Aucun remote point.</p>}
        {(points as RemotePointOut[]).map(pt => (
          <div key={pt.id}>
            <div className="flex items-center gap-3 px-4 py-3">
              <div className="shrink-0">{TYPE_ICON[pt.point_type]}</div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">{pt.label} <span className="text-xs text-gray-400">({pt.slug})</span></p>
                <p className="text-xs text-gray-500">
                  {pt.point_type.toUpperCase()} · {pt.username}@{pt.host}
                  {pt.git_repo ? ` · ${pt.git_repo}` : ''}
                  {' · '}{pt.auth_type === 'certificate' ? `cert:${pt.certificate_slug}` : pt.auth_storage === 'vault' ? 'vault' : 'local'}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => setEditing(e => e === pt.slug ? null : pt.slug)} className="text-xs text-indigo-600 hover:underline px-2 py-1">Éditer</button>
                <button onClick={() => delMut.mutate(pt.slug)} className="text-gray-300 hover:text-red-500 transition-colors p-1">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
            {editing === pt.slug && (
              <div className="px-4 pb-4">
                <PointForm
                  initial={pt}
                  certs={certs}
                  onSave={(body) => updateMut.mutate({ slug: pt.slug, body })}
                  onCancel={() => setEditing(null)}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Onglet Sauvegarde
// ─────────────────────────────────────────────────────────────────────────────

function RunStatus({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle className="h-4 w-4 text-green-500" />
  if (status === 'error') return <XCircle className="h-4 w-4 text-red-500" />
  return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
}

function JobCard({ job }: { job: BackupJobOut }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const { data: runs = [], refetch } = useQuery({
    queryKey: ['backup-runs', job.slug],
    queryFn: () => backupApi.listRuns(job.slug),
    enabled: expanded,
  })

  const delMut = useMutation({
    mutationFn: () => backupApi.deleteJob(job.slug),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['backup-jobs'] }),
  })
  const toggleMut = useMutation({
    mutationFn: () => backupApi.updateJob(job.slug, {
      label: job.label, strategy: job.strategy, enabled: !job.enabled,
      remote_point_slug: job.remote_point_slug, workspace_slug: job.workspace_slug,
      schedule_cron: job.schedule_cron, schedule_every_seconds: job.schedule_every_seconds,
      git_base_path: job.git_base_path,
    }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['backup-jobs'] }),
  })

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 bg-white">
        {job.strategy === 'git_sync'
          ? <GitBranch className="h-4 w-4 text-indigo-500 shrink-0" />
          : <HardDrive className="h-4 w-4 text-teal-500 shrink-0" />}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900">{job.label} <span className="text-xs text-gray-400">({job.slug})</span></p>
          <p className="text-xs text-gray-500">
            {job.strategy} · {job.remote_point_slug}
            {job.workspace_slug ? ` · ws:${job.workspace_slug}` : ' · toute instance'}
            {job.schedule_cron ? ` · cron: ${job.schedule_cron}` : ` · toutes les ${job.schedule_every_seconds}s`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {job.last_run_status && <RunStatus status={job.last_run_status} />}
          <button
            onClick={() => toggleMut.mutate()}
            className={`text-xs px-2 py-1 rounded-full font-medium ${job.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}
          >
            {job.enabled ? 'Actif' : 'Inactif'}
          </button>
          <button onClick={() => { setExpanded(v => !v); if (!expanded) void refetch() }} className="text-gray-400 hover:text-gray-600">
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
          <button onClick={() => delMut.mutate()} className="text-gray-300 hover:text-red-500 p-0.5">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-4 py-3">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Historique des runs</p>
          {(runs as BackupJobRunOut[]).length === 0 && <p className="text-xs text-gray-400">Aucun run enregistré.</p>}
          <div className="space-y-1">
            {(runs as BackupJobRunOut[]).map((r: BackupJobRunOut) => (
              <div key={r.id} className="flex items-center gap-2 text-xs">
                <RunStatus status={r.status} />
                <span className="text-gray-500">{new Date(r.started_at).toLocaleString()}</span>
                {r.status === 'success' && (
                  <span className="text-gray-700">
                    {r.files_written ?? 0} écrits · {r.files_deleted ?? 0} supprimés
                    {r.commit_sha ? ` · ${r.commit_sha}` : ' · rien à committer'}
                  </span>
                )}
                {r.status === 'error' && <span className="text-red-600 truncate">{r.error_message}</span>}
                {r.status === 'running' && <span className="text-blue-600">en cours…</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function BackupTab() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useQuery({ queryKey: ['backup-jobs'], queryFn: backupApi.listJobs, refetchInterval: 15000 })
  const { data: points = [] } = useQuery({ queryKey: ['remote-points'], queryFn: remotePointsApi.list })
  const [showForm, setShowForm] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [form, setForm] = useState<BackupJobBody & { slug: string }>({
    slug: '', label: '', strategy: 'git_sync', enabled: true,
    remote_point_slug: '', workspace_slug: null,
    schedule_cron: null, schedule_every_seconds: 3600,
    git_base_path: null,
  })
  const [scheduleMode, setScheduleMode] = useState<'interval' | 'cron'>('interval')

  const createMut = useMutation({
    mutationFn: () => {
      const body = { ...form, schedule_cron: scheduleMode === 'cron' ? form.schedule_cron : null, schedule_every_seconds: scheduleMode === 'interval' ? form.schedule_every_seconds : null }
      return backupApi.createJob(body as BackupJobBody & { slug: string })
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['backup-jobs'] }); setShowForm(false) },
    onError: (e) => setErr((e as Error).message),
  })

  const gitPoints = (points as RemotePointOut[]).filter(p => p.point_type === 'git')
  const dumpPoints = (points as RemotePointOut[]).filter(p => ['ftp', 'ftps', 'sftp'].includes(p.point_type))
  const availablePoints = form.strategy === 'git_sync' ? gitPoints : dumpPoints

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{(jobs as BackupJobOut[]).length} job{(jobs as BackupJobOut[]).length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => { setShowForm(v => !v); setErr(null) }}>
          <Plus className="h-3.5 w-3.5 mr-1" />{showForm ? 'Annuler' : 'Nouveau job'}
        </Button>
      </div>

      {showForm && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input placeholder="slug" value={form.slug} onChange={e => setForm(p => ({ ...p, slug: e.target.value }))} />
            <Input placeholder="Label" value={form.label} onChange={e => setForm(p => ({ ...p, label: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Stratégie</label>
              <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.strategy} onChange={e => setForm(p => ({ ...p, strategy: e.target.value as 'git_sync' | 'db_dump', remote_point_slug: '' }))}>
                <option value="git_sync">Sync git (documents)</option>
                <option value="db_dump">Dump DB (pg_dump)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Remote point</label>
              <select className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={form.remote_point_slug} onChange={e => setForm(p => ({ ...p, remote_point_slug: e.target.value }))}>
                <option value="">-- choisir --</option>
                {availablePoints.map((p: RemotePointOut) => <option key={p.slug} value={p.slug}>{p.label}</option>)}
              </select>
            </div>
          </div>
          <Input placeholder="Workspace (vide = toute l'instance)" value={form.workspace_slug ?? ''} onChange={e => setForm(p => ({ ...p, workspace_slug: e.target.value || null }))} />
          {form.strategy === 'git_sync' && (
            <Input placeholder="Sous-répertoire dans le repo (optionnel)" value={form.git_base_path ?? ''} onChange={e => setForm(p => ({ ...p, git_base_path: e.target.value || null }))} />
          )}
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Planification</label>
            <div className="flex gap-2">
              <select className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm" value={scheduleMode} onChange={e => setScheduleMode(e.target.value as 'interval' | 'cron')}>
                <option value="interval">Intervalle (secondes)</option>
                <option value="cron">Expression cron</option>
              </select>
              {scheduleMode === 'interval'
                ? <Input type="number" placeholder="3600" value={form.schedule_every_seconds ?? ''} onChange={e => setForm(p => ({ ...p, schedule_every_seconds: Number(e.target.value) || null }))} />
                : <Input placeholder="0 3 * * *" value={form.schedule_cron ?? ''} onChange={e => setForm(p => ({ ...p, schedule_cron: e.target.value || null }))} />
              }
            </div>
          </div>
          {err && <p className="text-xs text-red-600">{err}</p>}
          <Button size="sm" className="w-full" onClick={() => createMut.mutate()} disabled={createMut.isPending || !form.slug || !form.label || !form.remote_point_slug}>
            {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Créer le job'}
          </Button>
        </div>
      )}

      <div className="space-y-3">
        {(jobs as BackupJobOut[]).length === 0 && !showForm && <p className="text-sm text-gray-400 text-center py-6">Aucun job de sauvegarde configuré.</p>}
        {(jobs as BackupJobOut[]).map((j: BackupJobOut) => <JobCard key={j.id} job={j} />)}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Page principale
// ─────────────────────────────────────────────────────────────────────────────

type Tab = 'points' | 'certificates' | 'backup'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'points', label: 'Remote Points', icon: <Cpu className="h-4 w-4" /> },
  { id: 'certificates', label: 'Certificats', icon: <KeyRound className="h-4 w-4" /> },
  { id: 'backup', label: 'Sauvegarde', icon: <Clock className="h-4 w-4" /> },
]

export function RemotePage() {
  const [tab, setTab] = useState<Tab>('points')

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="mb-6 text-2xl font-semibold text-gray-900">Connexions & Sauvegarde</h1>

      <div className="mb-6 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
        {TABS.map(t => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={[
              'flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors',
              tab === t.id ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === 'points' && <RemotePointsTab />}
      {tab === 'certificates' && <CertificatesTab />}
      {tab === 'backup' && <BackupTab />}
    </div>
  )
}
