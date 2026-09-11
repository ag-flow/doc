/**
 * Suivi temps réel d'un document : flux SSE `/documents/{id}/watch`.
 *
 * `EventSource` ne porte pas de header Authorization : le flux est consommé
 * en fetch streaming (ReadableStream), avec reconnexion à backoff exponentiel
 * (1 s → 30 s). Le serveur émet l'état courant dès la connexion (test de vie)
 * et un keep-alive commenté ; `gone` termine le suivi (document supprimé).
 */
import { apiUrl } from './api'

export interface DocWatchEvent {
  document_id: string
  version: number
  updated_at: string
  updated_by: string | null
}

export interface DocWatchHandlers {
  onChange: (event: DocWatchEvent) => void
  onGone?: () => void
}

/** Découpe un tampon SSE en messages complets ; retourne le reste. */
export function drainSseBuffer(
  buffer: string,
  emit: (event: string | null, data: string | null) => void,
): string {
  let idx = buffer.indexOf('\n\n')
  while (idx >= 0) {
    const chunk = buffer.slice(0, idx)
    buffer = buffer.slice(idx + 2)
    if (!chunk.startsWith(':')) {
      const event = /^event: (.+)$/m.exec(chunk)?.[1] ?? null
      const data = /^data: (.+)$/m.exec(chunk)?.[1] ?? null
      emit(event, data)
    }
    idx = buffer.indexOf('\n\n')
  }
  return buffer
}

/** Démarre le suivi ; retourne la fonction d'arrêt (fermeture propre). */
export function watchDocument(
  ws: string,
  docId: string,
  handlers: DocWatchHandlers,
): () => void {
  const controller = new AbortController()
  let stopped = false
  let backoff = 1_000

  const finish = () => {
    stopped = true
    controller.abort()
  }

  const run = async () => {
    while (!stopped) {
      try {
        const res = await fetch(apiUrl(`/workspaces/${ws}/documents/${docId}/watch`), {
          // Le cookie de session HttpOnly accompagne la requête (même origine).
          credentials: 'include',
          signal: controller.signal,
        })
        if (!res.ok || !res.body) throw new Error(`watch ${res.status}`)
        backoff = 1_000
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          buffer = drainSseBuffer(buffer, (event, data) => {
            if (event === 'change' && data) {
              handlers.onChange(JSON.parse(data) as DocWatchEvent)
            } else if (event === 'gone') {
              handlers.onGone?.()
              finish()
            }
          })
          if (stopped) return
        }
      } catch {
        /* coupure réseau ou abort : la boucle décide */
      }
      if (stopped) return
      await new Promise((resolve) => setTimeout(resolve, backoff))
      backoff = Math.min(backoff * 2, 30_000)
    }
  }

  void run()
  return finish
}
