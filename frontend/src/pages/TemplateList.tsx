import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../lib/api'
import type { TemplateInfo } from '../lib/api'

export default function TemplateList() {
  const { t } = useTranslation()

  const { data, isLoading, isError } = useQuery<TemplateInfo[]>({
    queryKey: ['templates'],
    queryFn: () => api.get<TemplateInfo[]>('/templates'),
  })

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-gray-500" data-testid="loading">
        {t('common.loading')}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-6 text-sm text-red-600" data-testid="error">
        {t('error.generic')}
      </div>
    )
  }

  if (!data?.length) {
    return (
      <div className="p-6 text-center text-gray-400" data-testid="empty">
        <p className="text-lg font-medium mb-2">{t('tpl.emptyTitle')}</p>
        <p className="text-sm">{t('tpl.emptyHint')}</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="template-list">
      <h1 className="text-2xl font-bold mb-6">{t('tpl.title')}</h1>
      <div className="grid gap-4">
        {data.map(tpl => (
          <div
            key={tpl.template}
            className="border rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow"
            data-testid={`tpl-card-${tpl.template}`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-sm font-semibold text-indigo-700">
                {tpl.template}
              </span>
              <span className="font-mono text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">
                v{tpl.version}
              </span>
              <span className="text-gray-700 font-medium">{tpl.label}</span>
            </div>

            <div className="flex flex-wrap gap-1.5 mb-3">
              {tpl.type_slugs.map(slug => (
                <span
                  key={slug}
                  className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono"
                >
                  {slug}
                </span>
              ))}
            </div>

            <button
              className="text-sm text-indigo-600 hover:text-indigo-800 border border-indigo-200
                         hover:border-indigo-400 rounded px-3 py-1 transition-colors"
              disabled
              title={t('tpl.importDisabledHint')}
              data-testid={`import-btn-${tpl.template}`}
            >
              {t('tpl.importBtn')}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
