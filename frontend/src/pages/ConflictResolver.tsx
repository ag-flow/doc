import { useEffect, useRef, useState } from 'react'
import { EditorState } from '@codemirror/state'
import { EditorView, basicSetup } from 'codemirror'
import { MergeView } from '@codemirror/merge'
import { markdown } from '@codemirror/lang-markdown'
import './conflict.css'

export interface ConflictResolverProps {
  ancestor: string
  ancestorVersion: number
  server: string
  serverVersion: number
  draft: string
  onResolve: (merged: string, expectedVersion: number) => Promise<void>
  onCancel: () => void
}

const READONLY = [EditorView.editable.of(false), EditorState.readOnly.of(true)]
const COLLAPSE = { margin: 3, minSize: 4 }

export function ConflictResolver({
  ancestor, ancestorVersion, server, serverVersion, draft, onResolve, onCancel,
}: ConflictResolverProps) {
  const leftRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const draftView = useRef<EditorView | null>(null)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!leftRef.current || !rightRef.current) return

    const left = new MergeView({
      parent: leftRef.current,
      collapseUnchanged: COLLAPSE,
      a: { doc: ancestor, extensions: [basicSetup, markdown(), ...READONLY] },
      b: { doc: server,   extensions: [basicSetup, markdown(), ...READONLY] },
    })

    const right = new MergeView({
      parent: rightRef.current,
      collapseUnchanged: COLLAPSE,
      a: { doc: ancestor, extensions: [basicSetup, markdown(), ...READONLY] },
      b: { doc: draft,    extensions: [basicSetup, markdown()] },
    })
    draftView.current = right.b

    return () => {
      left.destroy()
      right.destroy()
      draftView.current = null
    }
  }, [ancestor, server, draft])

  async function handleSave() {
    const merged = draftView.current?.state.doc.toString() ?? draft
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
            Ce document a changé pendant ton édition (tu partais de la v{ancestorVersion},
            il est en v{serverVersion}). À gauche, ce que le serveur a modifié&nbsp;; à droite,
            ton brouillon, que tu ajustes. Puis enregistre sur la v{serverVersion}.
          </p>
        </header>

        <div className="conflict-panes">
          <section className="pane">
            <header className="pane-head">
              <span className="pane-label">Ancêtre v{ancestorVersion}</span>
              <span className="pane-arrow">⇄</span>
              <span className="pane-label pane-label--server">
                Serveur v{serverVersion} · lecture seule
              </span>
            </header>
            <div ref={leftRef} className="merge" />
          </section>

          <section className="pane">
            <header className="pane-head">
              <span className="pane-label">Ancêtre v{ancestorVersion}</span>
              <span className="pane-arrow">⇄</span>
              <span className="pane-label pane-label--draft">Ton brouillon · éditable</span>
            </header>
            <div ref={rightRef} className="merge" />
          </section>
        </div>

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
