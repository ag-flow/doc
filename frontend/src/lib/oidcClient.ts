import { oidcLoginApi } from './api'

/** Flow OIDC authorization-code côté navigateur.
 *
 *  Le navigateur ne fait que rediriger vers l'authorization_endpoint (découvert
 *  côté serveur) puis reposter le `code` au backend — l'échange du code et la
 *  vérification de l'id_token sont exclusivement serveur (AUTH-01). `state` lie
 *  le retour à la session du navigateur (anti-CSRF), `nonce` lie l'id_token au
 *  départ du flow.
 */

const STATE_KEY = 'docflow_oidc_state'
const NONCE_KEY = 'docflow_oidc_nonce'

export class OidcFlowError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'OidcFlowError'
  }
}

function randomToken(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function oidcRedirectUri(): string {
  return `${window.location.origin}/oidc/callback`
}

/** Démarre le flow : récupère la config publique puis redirige vers l'issuer. */
export async function beginOidcLogin(): Promise<void> {
  const cfg = await oidcLoginApi.config()
  if (!cfg?.enabled || !cfg.authorization_endpoint) {
    throw new OidcFlowError('OIDC non disponible')
  }
  const state = randomToken()
  const nonce = randomToken()
  sessionStorage.setItem(STATE_KEY, state)
  sessionStorage.setItem(NONCE_KEY, nonce)
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: cfg.client_id,
    redirect_uri: oidcRedirectUri(),
    scope: 'openid profile email',
    state,
    nonce,
  })
  window.location.assign(`${cfg.authorization_endpoint}?${params.toString()}`)
}

/** Termine le flow au retour de l'issuer : vérifie le state, poste le code au
 *  backend, retourne le JWT docflow. Le state/nonce sont consommés (one-shot). */
export async function completeOidcCallback(params: URLSearchParams): Promise<string> {
  const expectedState = sessionStorage.getItem(STATE_KEY)
  const nonce = sessionStorage.getItem(NONCE_KEY)
  sessionStorage.removeItem(STATE_KEY)
  sessionStorage.removeItem(NONCE_KEY)

  const idpError = params.get('error')
  if (idpError) throw new OidcFlowError(`refus de l'issuer: ${idpError}`)

  const code = params.get('code')
  const state = params.get('state')
  if (!code || !state || !expectedState || state !== expectedState) {
    throw new OidcFlowError('state OIDC absent ou invalide')
  }

  const res = await oidcLoginApi.callback({
    code,
    redirect_uri: oidcRedirectUri(),
    ...(nonce ? { nonce } : {}),
  })
  return res.access_token
}
