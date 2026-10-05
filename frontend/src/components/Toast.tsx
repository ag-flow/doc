import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { X, Warning, CheckCircle, Info } from '@phosphor-icons/react'

type Tone = 'error' | 'success' | 'info'
interface ToastItem { id: number; message: string; tone: Tone }
interface ToastCtxValue { toast: (message: string, tone?: Tone) => void }

const ToastCtx = createContext<ToastCtxValue>({ toast: () => {} })

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastCtxValue {
  return useContext(ToastCtx)
}

let _seq = 0

/** Accusés discrets : encre sur surface, magenta pour l'échec seulement. */
const TONE_STYLES: Record<Tone, string> = {
  error: 'text-accent-2-700',
  success: 'text-accent-700',
  info: 'text-ink/[0.75]',
}
const TONE_ICON = { error: Warning, success: CheckCircle, info: Info }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const remove = useCallback((id: number) => {
    setItems((t) => t.filter((x) => x.id !== id))
  }, [])

  const toast = useCallback(
    (message: string, tone: Tone = 'info') => {
      const id = ++_seq
      setItems((t) => [...t, { id, message, tone }])
      // Auto-fermeture : les erreurs restent plus longtemps (lecture).
      window.setTimeout(() => remove(id), tone === 'error' ? 12000 : 5000)
    },
    [remove],
  )

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      {/* En bas à GAUCHE : le coin droit porte les actions de page, et un accusé
          n'a pas à recouvrir un bouton. Disparition automatique, jamais de modale. */}
      <div className="pointer-events-none fixed bottom-4 left-4 z-[100] flex w-full max-w-md flex-col gap-2">
        {items.map((t) => {
          const Icon = TONE_ICON[t.tone]
          return (
            <div
              key={t.id}
              role="status"
              data-testid="toast"
              className={`card elev-md pointer-events-auto flex-row items-start gap-2 py-2.5 text-[13px] ${TONE_STYLES[t.tone]}`}
            >
              <Icon size={15} weight="duotone" className="mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{t.message}</span>
              <button
                type="button"
                onClick={() => remove(t.id)}
                aria-label="Fermer"
                className="shrink-0 border-0 bg-transparent p-0 text-inherit opacity-60 transition-opacity hover:opacity-100"
              >
                <X size={14} weight="bold" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
