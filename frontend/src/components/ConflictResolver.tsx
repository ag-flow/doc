import { useTranslation } from 'react-i18next'
import { Button } from './ui/button'

interface DocSnapshot {
  title: string
  content: string
}

interface ConflictResolverProps {
  ancestor: DocSnapshot
  server: DocSnapshot & { version: number }
  mine: DocSnapshot
  onKeepServer: (serverVersion: number) => void
  onKeepMine: () => void
  onClose: () => void
}

function Panel({ label, snapshot }: { label: string; snapshot: DocSnapshot }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <h3 className="mb-2 text-sm font-semibold text-gray-700">{label}</h3>
      <div className="mb-1 truncate text-sm font-medium text-gray-900" title={snapshot.title}>
        {snapshot.title}
      </div>
      <pre className="flex-1 overflow-auto rounded border border-gray-200 bg-gray-50 p-2 text-xs whitespace-pre-wrap">
        {snapshot.content}
      </pre>
    </div>
  )
}

export function ConflictResolver({
  ancestor,
  server,
  mine,
  onKeepServer,
  onKeepMine,
  onClose,
}: ConflictResolverProps) {
  const { t } = useTranslation()
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      data-testid="conflict-resolver"
    >
      <div className="flex max-h-[85vh] w-full max-w-5xl flex-col rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{t('editor.conflict.title')}</h2>
          <button
            className="text-sm text-gray-400 hover:text-gray-700"
            onClick={onClose}
            data-testid="conflict-close"
          >
            ✕
          </button>
        </div>
        <p className="mb-4 text-sm text-gray-600">{t('editor.conflict.desc')}</p>
        <div className="flex min-h-0 flex-1 gap-4">
          <Panel label={t('editor.conflict.ancestor')} snapshot={ancestor} />
          <Panel label={t('editor.conflict.server')} snapshot={server} />
          <Panel label={t('editor.conflict.mine')} snapshot={mine} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => onKeepServer(server.version)}
            data-testid="conflict-keep-server"
          >
            {t('editor.conflict.keepServer')}
          </Button>
          <Button onClick={onKeepMine} data-testid="conflict-keep-mine">
            {t('editor.conflict.keepMine')}
          </Button>
        </div>
      </div>
    </div>
  )
}
