import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { referencesApi, type BacklinkOut } from '../lib/api'

interface BacklinksPanelProps {
  ws: string
  docId: string
  blocSlug?: string
}

export function BacklinksPanel({ ws, docId, blocSlug }: BacklinksPanelProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { data: backlinks = [], isLoading } = useQuery<BacklinkOut[]>({
    queryKey: ['backlinks', ws, docId],
    queryFn: () => referencesApi.getBacklinks(ws, docId),
    enabled: Boolean(ws && docId),
    staleTime: 30_000,
  })

  if (isLoading) return null
  if (backlinks.length === 0) {
    return (
      <aside className="mt-6 w-full" data-testid="backlinks-panel">
        <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase">
          {t('backlinks.title', 'Référencé par')}
        </h2>
        <p className="text-sm text-gray-400">
          {t('backlinks.empty', 'Aucune référence entrante')}
        </p>
      </aside>
    )
  }

  return (
    <aside className="mt-6 w-full" data-testid="backlinks-panel">
      <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase">
        {t('backlinks.title', 'Référencé par')} ({backlinks.length})
      </h2>
      <ul className="space-y-2">
        {backlinks.map((bl) => (
          <li key={bl.source_id} className="rounded border border-gray-100 bg-gray-50 p-2">
            <button
              className="block w-full text-left text-sm font-medium text-blue-600 hover:underline"
              onClick={() => {
                const path = blocSlug
                  ? `/ws/${ws}/blocs/${blocSlug}/documents/${bl.source_id}`
                  : `/ws/${ws}/documents/${bl.source_id}`
                navigate(path)
              }}
              data-testid={`backlink-${bl.source_id}`}
            >
              {bl.source_title}
            </button>
            {(bl.source_type || bl.bloc) && (
              <p className="mt-0.5 text-xs text-gray-400">
                {[bl.source_type, bl.target_label].filter(Boolean).join(' · ')}
              </p>
            )}
          </li>
        ))}
      </ul>
    </aside>
  )
}
