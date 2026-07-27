import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from '@phosphor-icons/react'
import { docsApi, type DocumentVersionInfo, type DocumentVersionOut } from '../lib/api'
import { relativeDate } from '../lib/relativeDate'
import { TableSkeleton } from './ui/states'

/**
 * Historique des versions d'un document : liste à gauche (numéro, titre, date,
 * taille), contenu de la version sélectionnée à droite, en lecture seule.
 * Restaurer une version = la copier puis coller — pas de rollback silencieux
 * qui écraserait le travail courant.
 */
export function VersionHistoryDialog({ ws, docId, currentVersion, onClose }: {
  ws: string
  docId: string
  currentVersion: number
  onClose: () => void
}) {
  const [selected, setSelected] = useState<number | null>(null)

  const { data: versions = [], isLoading } = useQuery<DocumentVersionInfo[]>({
    queryKey: ['doc-versions', ws, docId],
    queryFn: () => docsApi.listVersions(ws, docId),
  })

  const shown = selected ?? versions[0]?.version_number ?? null
  const { data: version } = useQuery<DocumentVersionOut>({
    queryKey: ['doc-version', ws, docId, shown],
    queryFn: () => docsApi.getVersion(ws, docId, shown!),
    enabled: shown !== null,
  })

  return (
    <div className="dialog-backdrop z-50" onClick={onClose}>
      <div
        className="dialog h-[min(88vh,800px)] w-full !max-w-4xl"
        role="dialog"
        aria-modal="true"
        aria-label="Historique des versions"
        onClick={(e) => e.stopPropagation()}
        data-testid="version-history"
      >
        <div className="flex items-center justify-between">
          <h4 className="dialog-title m-0">Historique des versions</h4>
          <button type="button" onClick={onClose} aria-label="Fermer" title="Fermer"
            className="border-0 bg-transparent p-1 text-ink/[0.4] hover:text-ink">
            <X size={16} weight="bold" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
          <ul className="dialog-scroll m-0 list-none overflow-y-auto p-0">
            {isLoading ? (
              <TableSkeleton rows={4} columns={1} />
            ) : (
              versions.map((v) => (
                <li key={v.version_number}>
                  <button
                    type="button"
                    onClick={() => setSelected(v.version_number)}
                    aria-current={shown === v.version_number ? 'true' : undefined}
                    className={`w-full rounded-md border-0 px-3 py-2 text-left ${
                      shown === v.version_number ? 'bg-accent-100' : 'bg-transparent hover:bg-ink/[0.04]'
                    }`}
                    data-testid={`version-item-${v.version_number}`}
                  >
                    <span className="flex items-baseline gap-2">
                      <span className="font-[600] [font-family:var(--font-heading)]">
                        v{v.version_number}
                      </span>
                      {v.version_number === currentVersion && (
                        <span className="tag tag-accent text-[10px]">courante</span>
                      )}
                      <span className="ml-auto text-[11px] text-ink/[0.45]">
                        {relativeDate(v.created_at)}
                      </span>
                    </span>
                    <span className="block truncate text-[13px] text-ink/[0.6]">{v.title}</span>
                  </button>
                </li>
              ))
            )}
          </ul>

          <div className="dialog-scroll min-h-0 overflow-y-auto rounded-md bg-neutral-100 p-4">
            {version ? (
              <>
                <h5 className="mt-0">{version.title}</h5>
                <pre className="m-0 whitespace-pre-wrap break-words text-[13px] leading-[1.6] [font-family:var(--font-mono)]"
                  data-testid="version-content">
                  {version.content || '(document vide)'}
                </pre>
              </>
            ) : (
              <p className="text-muted text-[13px]">Sélectionnez une version.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
