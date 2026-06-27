import { useEffect, useRef, useState } from 'react'
import { EditorView, basicSetup } from 'codemirror'
import { unifiedMergeView } from '@codemirror/merge'
import { markdown } from '@codemirror/lang-markdown'
import './conflict.css'

export interface ConflictResolverProps {
  baseVersion: number
  server: string
  serverVersion: number
  draft: string
  onResolve: (merged: string, expectedVersion: number) => Promise<void>
  onCancel: () => void
}

const COLLAPSE = { margin: 3, minSize: 4 }

export function ConflictResolver({
  baseVersion, server, serverVersion, draft, onResolve, onCancel,
}: ConflictResolverProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!hostRef.current) return
    const view = new EditorView({
      parent: hostRef.current,
      doc: draft,
      extensions: [
        basicSetup,
        markdown(),
        unifiedMergeView({
          original: server,
          mergeControls: true,
          collapseUnchanged: COLLAPSE,
        }),
      ],
    })
    viewRef.current = view
    return () => { view.destroy(); viewRef.current = null }
  }, [server, draft])

  async function handleSave() {
    const merged = viewRef.current?.state.doc.toString() ?? draft
    setSaving(true)
    setError(null)
    try {
      await onResolve(merged, serverVersion)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 p-4" data-testid="conflict-resolver">
      <div className="conflict">
        <header className="conflict-head">
          <p className="conflict-title">Conflit de version</p>
          <p className="muted">
            Ce document a changé pendant ton édition (tu partais de la v{baseVersion},
            il est en v{serverVersion}). Les différences entre le serveur et ton texte
            sont surlignées : accepte, rejette ou édite chaque bloc, puis enregistre
            sur la v{serverVersion}.
          </p>
        </header>

        <div ref={hostRef} className="merge merge--single" />

        {error && <p className="conflict-error">{error}</p>}

        <footer className="conflict-foot">
          <button className="btn btn--ghost" onClick={onCancel} disabled={saving}>
            Annuler
          </button>
          <button className="btn" onClick={() => void handleSave()} disabled={saving}>
            {saving ? 'Enregistrement…' : `Enregistrer sur v${serverVersion}`}
          </button>
        </footer>
      </div>
    </div>
  )
}
