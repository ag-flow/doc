import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, RefreshCw } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { useToast } from '../components/Toast'
import { meApi, type MeProfileOut } from '../lib/api'

/**
 * « Mon profil » : email (clé de rattachement à la connexion OIDC) et GUID
 * d'identité OBO (contrat v6) — le MÊME GUID doit être posé dans le profil du
 * portail pour que les appels MCP soient attribués à l'utilisateur.
 */
export function MyProfilePage() {
  const qc = useQueryClient()
  const { toast } = useToast()

  const { data: profile, isLoading } = useQuery<MeProfileOut>({
    queryKey: ['me-profile'],
    queryFn: () => meApi.get(),
  })

  const [email, setEmail] = useState('')
  const [identity, setIdentity] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (profile) {
      setEmail(profile.email)
      setIdentity(profile.identity ?? '')
    }
  }, [profile])

  const saveMutation = useMutation({
    mutationFn: () => meApi.update({ email: email.trim(), identity: identity.trim() }),
    onSuccess: (updated) => {
      qc.setQueryData(['me-profile'], updated)
      toast('Profil enregistré.', 'success')
    },
    onError: (e: Error) => toast(`Enregistrement échoué : ${e.message}`, 'error'),
  })

  async function copyIdentity() {
    try {
      await navigator.clipboard?.writeText(identity)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch { /* presse-papier indisponible */ }
  }

  if (isLoading) return <div className="p-8 text-gray-500">Chargement…</div>

  return (
    <div className="max-w-2xl p-8" data-testid="my-profile">
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">Mon profil</h1>
      <p className="mb-6 text-sm text-gray-500">
        {profile?.label} — compte {profile?.source === 'oidc' ? 'OIDC' : 'local'}
        {profile?.is_admin ? ' · superadmin' : ''}
      </p>

      <div className="space-y-6 rounded-lg border border-gray-200 bg-white p-6">
        {/* Email */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Email</label>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="prenom.nom@example.com"
            data-testid="me-email"
          />
          <p className="mt-1 text-xs text-gray-400">
            Sert au rattachement de votre compte à la connexion <strong>OIDC</strong> :
            à la première connexion SSO, le compte portant cet email (vérifié par
            l'IdP) est lié automatiquement.
          </p>
        </div>

        {/* Identité OBO */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Identité (GUID) — attribution des appels MCP
          </label>
          <div className="flex items-center gap-2">
            <Input
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder="ex. 6f9619ff-8b86-d011-b42d-00c04fc964ff"
              className="font-mono text-sm"
              data-testid="me-identity"
            />
            <Button
              variant="secondary"
              onClick={() => setIdentity(crypto.randomUUID())}
              title="Générer un GUID"
              data-testid="me-identity-generate"
              className="inline-flex shrink-0 items-center gap-1.5"
            >
              <RefreshCw size={14} /> Générer
            </Button>
            <button
              type="button"
              onClick={copyIdentity}
              disabled={!identity.trim()}
              title="Copier le GUID"
              data-testid="me-identity-copy"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40"
            >
              {copied ? <Check size={15} className="text-green-600" /> : <Copy size={15} />}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-400">
            Posez <strong>le même GUID</strong> dans votre profil du <strong>portail</strong> :
            les appels MCP relayés en votre nom (<span className="font-mono">x-portal-actor</span>)
            vous seront attribués. Vide = appels non attribués (imputés à la clé API).
          </p>
        </div>

        <div className="pt-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !email.trim()}
            data-testid="me-save"
          >
            {saveMutation.isPending ? 'Enregistrement…' : 'Enregistrer'}
          </Button>
        </div>
      </div>
    </div>
  )
}
