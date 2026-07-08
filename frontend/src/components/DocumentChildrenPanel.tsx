import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { docsApi, type AllowedTypeOut, type DocumentOut } from '../lib/api'
import { AddDocumentDialog } from './AddDocumentDialog'
import { Button } from './ui/button'

interface Props {
  ws: string
  blocSlug: string
  docId: string
}

export function DocumentChildrenPanel({ ws, blocSlug, docId }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [creatingChild, setCreatingChild] = useState<AllowedTypeOut | null>(null)

  const { data: blockDocs = [] } = useQuery<DocumentOut[]>({
    queryKey: ['block-documents', ws, blocSlug],
    queryFn: () => docsApi.getBlockDocuments(ws, blocSlug),
  })

  const { data: childTypes = [] } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, blocSlug, docId],
    queryFn: () => docsApi.getAllowedTypes(ws, blocSlug, docId),
  })

  const children = blockDocs.filter((d) => d.parent_id === docId)

  const docPath = (id: string) => `/ws/${ws}/blocs/${blocSlug}/documents/${id}`

  function handleChildCreated(newDocId: string) {
    setCreatingChild(null)
    void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, blocSlug] })
    void queryClient.invalidateQueries({ queryKey: ['block-values', ws, blocSlug] })
    void navigate(docPath(newDocId))
  }

  if (childTypes.length === 0 && children.length === 0) return null

  return (
    <div className="mt-6 border-t border-gray-100 pt-4">
      {children.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-500 uppercase tracking-wide">
            {t('documents.children')}
          </h3>
          <ul className="space-y-1">
            {children.map((child) => (
              <li key={child.doc_technical_key} className="flex items-center gap-2">
                <button
                  className="flex-1 text-left text-sm text-indigo-600 hover:underline truncate"
                  onClick={() => void navigate(docPath(child.doc_technical_key))}
                  data-testid={`child-link-${child.doc_technical_key}`}
                >
                  {child.title}
                  {child.functional_type_slug && (
                    <span className="ml-2 text-xs text-gray-400 font-mono">
                      {child.functional_type_slug}
                    </span>
                  )}
                </button>
                <a
                  href={docPath(child.doc_technical_key)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-gray-400 hover:text-gray-700 text-xs"
                  title={t('documents.openNewTab')}
                  onClick={(e) => e.stopPropagation()}
                  data-testid={`child-newtab-${child.doc_technical_key}`}
                >
                  ↗
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {childTypes.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-400">{t('documents.addChild')}</span>
          {childTypes.map((ct) => (
            <Button
              key={ct.slug}
              variant="secondary"
              size="sm"
              data-testid={`add-child-${ct.slug}`}
              onClick={() => setCreatingChild(ct)}
            >
              + {ct.label}
            </Button>
          ))}
        </div>
      )}

      {creatingChild && (
        <AddDocumentDialog
          ws={ws}
          block={blocSlug}
          parentId={docId}
          initialType={creatingChild.slug}
          onCreated={handleChildCreated}
          onClose={() => setCreatingChild(null)}
        />
      )}
    </div>
  )
}
