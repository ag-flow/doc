import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowClockwise, Check, Copy } from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { SectionHead } from '../components/SectionHead'
import { SheetSkeleton } from '../components/ui/states'
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

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
        <SheetSkeleton />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24" data-testid="my-profile">
      <SectionHead kicker="Administration" title="Mon profil" />
      <p className="mb-8 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {profile?.label} — compte {profile?.source === 'oidc' ? 'OIDC' : 'local'}
        {profile?.is_admin ? ' · superadmin' : ''}
      </p>

      <div className="max-w-[560px] space-y-8">
        {/* Email */}
        <div className="field">
          <label htmlFor="me-email">Email</label>
          <Input
            id="me-email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="prenom.nom@example.com"
            data-testid="me-email"
          />
          <p className="field-hint m-0">
            Sert au rattachement de votre compte à la connexion <strong>OIDC</strong> :
            à la première connexion SSO, le compte portant cet email (vérifié par
            l'IdP) est lié automatiquement.
          </p>
        </div>

        {/* Identité OBO */}
        <div className="field">
          <label htmlFor="me-identity">Identité (GUID) — attribution des appels MCP</label>
          <div className="flex items-center gap-2">
            <Input
              id="me-identity"
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder="ex. 6f9619ff-8b86-d011-b42d-00c04fc964ff"
              className="text-[13px] [font-family:var(--font-mono)]"
              data-testid="me-identity"
            />
            <Button
              variant="secondary"
              onClick={() => setIdentity(crypto.randomUUID())}
              title="Générer un GUID"
              data-testid="me-identity-generate"
              className="shrink-0"
            >
              <ArrowClockwise size={14} weight="duotone" /> Générer
            </Button>
            <Button
              variant="icon"
              onClick={() => void copyIdentity()}
              disabled={!identity.trim()}
              title="Copier le GUID"
              data-testid="me-identity-copy"
              className="shrink-0"
            >
              {copied
                ? <Check size={15} weight="bold" className="text-accent-700" />
                : <Copy size={15} weight="duotone" />}
            </Button>
          </div>
          <p className="field-hint m-0">
            Posez <strong>le même GUID</strong> dans votre profil du <strong>portail</strong> :
            les appels MCP relayés en votre nom (
            <span className="[font-family:var(--font-mono)]">x-portal-actor</span>)
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
