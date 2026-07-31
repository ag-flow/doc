import { useEffect, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Printer } from '@phosphor-icons/react'
import { docsApi, type DocumentOut } from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { MarkdownViewer } from '../components/MarkdownViewer'
import { stripTitleHeading } from '../lib/markdownTitle'
import { Button } from '../components/ui/button'
import { SheetSkeleton } from '../components/ui/states'

/**
 * Vue d'impression (export PDF sans Chromium serveur) : la page rend le
 * document et les enfants choisis avec le VRAI moteur de l'application —
 * composants graphiques compris (df-chart, mermaid, df-display…) — dans un
 * onglet dédié sans chrome. L'utilisateur vérifie le rendu puis déclenche
 * l'impression du navigateur (destination « Enregistrer en PDF »).
 */
export function PrintDocumentPage() {
  const { wsSlug: ws, docId } = useParams<{ wsSlug: string; blocSlug: string; docId: string }>()
  const [params] = useSearchParams()
  const signed = params.get('signed') === 'true'
  const childrenParam = params.get('children') ?? ''

  // Les blocs branchés sur un dataset résolvent le workspace via le contexte.
  const { setCurrentSlug } = useWorkspace()
  useEffect(() => {
    if (ws) setCurrentSlug(ws)
  }, [ws, setCurrentSlug])

  const ids = useMemo(
    () => [docId!, ...childrenParam.split(',').filter(Boolean)],
    [docId, childrenParam],
  )

  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['document', ws, id],
      queryFn: () => docsApi.getDocument(ws!, id),
      enabled: Boolean(ws && id),
    })),
  })
  const loading = queries.some((q) => q.isLoading)
  const failed = queries.some((q) => q.isError)
  const docs = queries
    .map((q) => q.data)
    .filter((d): d is DocumentOut => Boolean(d))

  return (
    <div className="print-page" data-testid="print-page">
      <div className="no-print print-toolbar">
        <p className="m-0 min-w-0 flex-1 text-[13px] text-ink/[0.6]">
          Vérifiez le rendu (les diagrammes se dessinent en un instant), puis
          imprimez — choisissez « Enregistrer en PDF » comme destination.
        </p>
        <Button onClick={() => window.print()} data-testid="print-btn">
          <Printer size={15} weight="duotone" /> Imprimer / PDF
        </Button>
      </div>

      {failed && (
        <p className="field-error" data-testid="print-error">
          Impossible de charger un des documents demandés.
        </p>
      )}
      {loading ? (
        <SheetSkeleton />
      ) : (
        <>
          {docs.map((d, i) => (
            <section
              key={d.doc_technical_key}
              className={`doc-sheet wiki-prose print-sheet${i > 0 ? ' print-break' : ''}`}
              data-testid={`print-doc-${d.doc_technical_key}`}
            >
              <h1>{d.title}</h1>
              <MarkdownViewer content={stripTitleHeading(d.content ?? '', d.title)} bare />
            </section>
          ))}
          {signed && (
            <section className="print-signatures" data-testid="print-signatures">
              <h2>Signatures</h2>
              <table>
                <tbody>
                  <tr>
                    <td className="sig-label">Nom</td>
                    <td className="sig-label">Date</td>
                    <td className="sig-label">Signature</td>
                  </tr>
                  <tr><td /><td /><td /></tr>
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </div>
  )
}
