import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, FileText } from 'lucide-react'
import { publicApi, type DocumentOut } from '../lib/api'
import { MarkdownViewer } from '../components/MarkdownViewer'

function AncestorChain({ docId }: { docId: string }) {
  const { data: doc } = useQuery<DocumentOut>({
    queryKey: ['pub-doc', docId],
    queryFn: () => publicApi.getDocument(docId),
  })
  if (!doc) return null
  return (
    <>
      {doc.parent_id && <AncestorChain docId={doc.parent_id} />}
      <ChevronRight size={13} className="text-gray-300 shrink-0" />
      <Link
        to={`/pub/${doc.doc_technical_key}`}
        className="text-gray-500 hover:text-gray-700 transition-colors"
      >
        {doc.title}
      </Link>
    </>
  )
}

export function PublicDocumentViewer() {
  const { docId } = useParams<{ docId: string }>()

  const { data: doc, isLoading, isError } = useQuery<DocumentOut>({
    queryKey: ['pub-doc', docId],
    queryFn: () => publicApi.getDocument(docId!),
    enabled: Boolean(docId),
    retry: false,
  })

  const { data: children = [] } = useQuery<DocumentOut[]>({
    queryKey: ['pub-children', docId],
    queryFn: () => publicApi.getChildren(docId!),
    enabled: Boolean(docId && doc),
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-400">
        Chargement…
      </div>
    )
  }

  if (isError || !doc) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="text-lg font-medium text-gray-700">Document introuvable</p>
          <p className="mt-1 text-sm text-gray-400">Ce document n'existe pas ou n'est pas public.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white">
      {/* En-tête fil de hiérarchie */}
      <header className="border-b border-gray-100 px-6 py-2.5">
        <div className="mx-auto flex max-w-4xl items-center gap-1 text-sm">
          {doc.parent_id && <AncestorChain docId={doc.parent_id} />}
          {doc.parent_id && <ChevronRight size={13} className="text-gray-300 shrink-0" />}
          <span className="font-medium text-gray-800">{doc.title}</span>
        </div>
      </header>

      {/* Contenu */}
      <main className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">{doc.title}</h1>
        {doc.content ? (
          <MarkdownViewer content={doc.content} />
        ) : (
          <p className="text-sm text-gray-400 italic">Aucun contenu.</p>
        )}

        {/* Enfants */}
        {children.length > 0 && (
          <section className="mt-10">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
              Contenu
            </h2>
            <ul className="space-y-1">
              {children.map((child) => (
                <li key={child.doc_technical_key}>
                  <Link
                    to={`/pub/${child.doc_technical_key}`}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-gray-700
                               hover:bg-gray-50 hover:text-gray-900 transition-colors"
                  >
                    <FileText size={14} className="text-gray-400 shrink-0" />
                    {child.title}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  )
}
