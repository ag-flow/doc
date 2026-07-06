import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, type AppUserOut } from '../lib/api'
import { Button } from '../components/ui/button'

function SourceBadge({ source }: { source: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
      source === 'oidc'
        ? 'bg-purple-100 text-purple-700'
        : 'bg-gray-100 text-gray-600'
    }`}>
      {source}
    </span>
  )
}

function StatusBadge({ user }: { user: AppUserOut }) {
  if (user.disabled) return <span className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-700 font-medium">désactivé</span>
  if (!user.validated) return <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">en attente</span>
  if (user.is_admin) return <span className="text-xs px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 font-medium">admin</span>
  return <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 font-medium">validé</span>
}

export function UsersAdmin() {
  const qc = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const { data: users = [], isLoading } = useQuery<AppUserOut[]>({
    queryKey: ['admin-users'],
    queryFn: () => usersApi.list(),
  })

  const validateMut = useMutation({
    mutationFn: (id: string) => usersApi.validate(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })

  const unvalidateMut = useMutation({
    mutationFn: (id: string) => usersApi.unvalidate(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin-users'] })
      setConfirmDelete(null)
    },
  })

  if (isLoading) return <p className="p-6 text-sm text-gray-400">Chargement…</p>

  const pending = users.filter(u => !u.validated && !u.disabled)
  const rest = users.filter(u => u.validated || u.disabled)

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Utilisateurs</h1>
      <p className="text-sm text-gray-500 mb-6">
        Les utilisateurs qui se connectent via Keycloak arrivent en attente de validation.
        Validez-les manuellement pour leur donner accès à l'application.
      </p>

      {/* ── En attente ── */}
      {pending.length > 0 && (
        <section className="mb-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-600 mb-3">
            En attente de validation ({pending.length})
          </h2>
          <div className="space-y-2">
            {pending.map(user => (
              <UserRow
                key={user.id}
                user={user}
                onValidate={() => validateMut.mutate(user.id)}
                onDelete={() => setConfirmDelete(user.id)}
                confirmDelete={confirmDelete}
                setConfirmDelete={setConfirmDelete}
                onConfirmDelete={() => deleteMut.mutate(user.id)}
                busy={validateMut.isPending || deleteMut.isPending}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── Actifs / désactivés ── */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 mb-3">
          Tous les utilisateurs ({rest.length})
        </h2>
        {rest.length === 0 ? (
          <p className="text-sm text-gray-400">Aucun utilisateur.</p>
        ) : (
          <div className="space-y-2">
            {rest.map(user => (
              <UserRow
                key={user.id}
                user={user}
                onUnvalidate={user.validated && !user.is_admin ? () => unvalidateMut.mutate(user.id) : undefined}
                onDelete={() => setConfirmDelete(user.id)}
                confirmDelete={confirmDelete}
                setConfirmDelete={setConfirmDelete}
                onConfirmDelete={() => deleteMut.mutate(user.id)}
                busy={unvalidateMut.isPending || deleteMut.isPending}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function UserRow({
  user,
  onValidate,
  onUnvalidate,
  onDelete,
  confirmDelete,
  setConfirmDelete,
  onConfirmDelete,
  busy,
}: {
  user: AppUserOut
  onValidate?: () => void
  onUnvalidate?: () => void
  onDelete: () => void
  confirmDelete: string | null
  setConfirmDelete: (id: string | null) => void
  onConfirmDelete: () => void
  busy: boolean
}) {
  const isConfirming = confirmDelete === user.id

  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm text-gray-900">{user.label}</span>
          {user.username && user.username !== user.label && (
            <span className="text-xs text-gray-400 font-mono">@{user.username}</span>
          )}
          <StatusBadge user={user} />
          <SourceBadge source={user.source} />
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{user.email}</p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {onValidate && (
          <Button size="sm" onClick={onValidate} disabled={busy} data-testid={`validate-${user.id}`}>
            Valider
          </Button>
        )}
        {onUnvalidate && (
          <Button size="sm" variant="secondary" onClick={onUnvalidate} disabled={busy}>
            Révoquer
          </Button>
        )}
        {!isConfirming ? (
          !user.is_admin && (
            <button
              className="text-xs text-gray-400 hover:text-red-500 transition-colors px-1"
              onClick={onDelete}
              disabled={busy}
            >
              Supprimer
            </button>
          )
        ) : (
          <div className="flex items-center gap-1">
            <span className="text-xs text-red-600">Confirmer ?</span>
            <button
              className="text-xs text-red-600 font-semibold hover:underline"
              onClick={onConfirmDelete}
              disabled={busy}
            >
              Oui
            </button>
            <button
              className="text-xs text-gray-400 hover:underline"
              onClick={() => setConfirmDelete(null)}
            >
              Non
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
