import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { X, AlertCircle, CheckCircle2, Info } from 'lucide-react'

type Tone = 'error' | 'success' | 'info'
interface ToastItem { id: number; message: string; tone: Tone }
interface ToastCtxValue { toast: (message: string, tone?: Tone) => void }

const ToastCtx = createContext<ToastCtxValue>({ toast: () => {} })

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastCtxValue {
  return useContext(ToastCtx)
}

let _seq = 0

const TONE_STYLES: Record<Tone, string> = {
  error: 'border-red-200 bg-red-50 text-red-800',
  success: 'border-green-200 bg-green-50 text-green-800',
  info: 'border-gray-200 bg-white text-gray-800',
}
const TONE_ICON = { error: AlertCircle, success: CheckCircle2, info: Info }

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
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-md flex-col gap-2">
        {items.map((t) => {
          const Icon = TONE_ICON[t.tone]
          return (
            <div
              key={t.id}
              role="alert"
              data-testid="toast"
              className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-4 py-3 text-sm shadow-lg ${TONE_STYLES[t.tone]}`}
            >
              <Icon size={16} className="mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{t.message}</span>
              <button
                type="button"
                onClick={() => remove(t.id)}
                aria-label="Fermer"
                className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
              >
                <X size={15} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
