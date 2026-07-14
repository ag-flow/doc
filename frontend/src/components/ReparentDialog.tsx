import { useEffect, useState } from 'react'
import { type AllowedTypeOut, type DocumentOut, docsApi } from '../lib/api'
import { applyReparent, planReparent } from '../lib/reparent'
import { Button } from './ui/button'

/** Fenêtre de déplacement d'un document.
 *
 *  Deux entrées :
 *  - fiche (« Déplacer ») : `newParentId === undefined` → étape 1 de choix du
 *    parent (liste des documents du bloc + racine), puis conversion éventuelle ;
 *  - drag & drop de la vue liste : `newParentId` fourni → passe directement à
 *    la conversion (la fenêtre ne s'affiche que si plusieurs types candidats).
 *
 *  Conversion : si le type actuel n'est pas accepté à la destination, un seul
 *  candidat = conversion annoncée puis appliquée ; plusieurs = choix demandé.
 */
export function ReparentDialog({
  ws,
  block,
  doc,
  newParentId,
  onDone,
  onCancel,
}: {
  ws: string
  block: string
  doc: { id: string; title: string; type: string | null }
  /** undefined = demander le parent ; string|null = destination imposée (DnD). */
  newParentId?: string | null
  onDone: () => void
  onCancel: () => void
}) {
  const [parentChoice, setParentChoice] = useState<string | null | undefined>(newParentId)
  const [candidates, setCandidates] = useState<AllowedTypeOut[] | null>(null)
  const [chosenType, setChosenType] = useState('')
  const [docs, setDocs] = useState<DocumentOut[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Étape 1 (fiche) : charger les parents possibles du bloc
  useEffect(() => {
    if (newParentId === undefined) {
      docsApi.getBlockDocuments(ws, block).then(setDocs).catch(() => setDocs([]))
    }
  }, [ws, block, newParentId])

  async function moveTo(target: string | null) {
    setBusy(true)
    setError(null)
    try {
      const plan = await planReparent(ws, block, doc.type, target)
      if (plan.typeAccepted) {
        await applyReparent(ws, doc.id, target)
        onDone()
        return
      }
      if (plan.allowed.length === 0) {
        setError('Aucun type accepté à cet emplacement (position feuille).')
        return
      }
      if (plan.allowed.length === 1) {
        await applyReparent(ws, doc.id, target, plan.allowed[0].slug)
        onDone()
        return
      }
      // Plusieurs candidats : demander le type cible
      setParentChoice(target)
      setCandidates(plan.allowed)
      setChosenType(plan.allowed[0].slug)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // DnD : destination imposée → planifier immédiatement au montage
  useEffect(() => {
    if (newParentId !== undefined) void moveTo(newParentId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function confirmType() {
    setBusy(true)
    setError(null)
    try {
      await applyReparent(ws, doc.id, parentChoice ?? null, chosenType)
      onDone()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // DnD sans conversion à demander : rien à afficher (moveTo gère et ferme)
  if (newParentId !== undefined && candidates === null && !error) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md space-y-4 rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-bold text-gray-900">
          Déplacer « {doc.title} »
        </h2>

        {candidates === null && newParentId === undefined && (
          <div className="space-y-2">
            <p className="text-sm text-gray-600">Choisir le nouveau parent :</p>
            <div className="max-h-64 overflow-y-auto rounded border border-gray-200 divide-y divide-gray-100">
              <button
                className="w-full px-3 py-2 text-left text-sm hover:bg-indigo-50"
                disabled={busy}
                onClick={() => void moveTo(null)}
                data-testid="reparent-root"
              >
                ⬆ Racine du bloc
              </button>
              {docs.filter((d) => d.doc_technical_key !== doc.id).map((d) => (
                <button
                  key={d.doc_technical_key}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-indigo-50"
                  disabled={busy}
                  onClick={() => void moveTo(d.doc_technical_key)}
                  data-testid={`reparent-to-${d.slug ?? d.doc_technical_key}`}
                >
                  {d.title} <span className="text-xs text-gray-400">({d.type})</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {candidates !== null && (
          <div className="space-y-2">
            <p className="text-sm text-gray-600">
              Le type « {doc.type} » n'est pas accepté à cet emplacement — le
              document sera <span className="font-medium">converti</span>.
              Choisir le type cible :
            </p>
            <div className="space-y-1">
              {candidates.map((t) => (
                <label key={t.slug} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="target-type"
                    value={t.slug}
                    checked={chosenType === t.slug}
                    onChange={() => setChosenType(t.slug)}
                  />
                  {t.label} <span className="text-xs text-gray-400">({t.slug})</span>
                </label>
              ))}
            </div>
            <p className="text-xs text-amber-700">
              Les valeurs de propriétés qui n'existent pas sur le type cible
              seront supprimées.
            </p>
          </div>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            Annuler
          </Button>
          {candidates !== null && (
            <Button size="sm" onClick={() => void confirmType()} disabled={busy} data-testid="reparent-confirm">
              Convertir et déplacer
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
