import { createReactBlockSpec } from '@blocknote/react'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { BlockFrame } from './BlockFrame'
import { DatasetGrid } from './DatasetGrid'

/** Rend la grille d'un dataset référencé, en résolvant le workspace via le contexte. */
function DatasetBlockView({ datasetId, editable }: { datasetId: string; editable: boolean }) {
  const { t } = useTranslation()
  const { currentSlug } = useWorkspace()
  if (!datasetId)
    return (
      <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
        {t('dataset.missingRef')}
      </div>
    )
  if (!currentSlug)
    return (
      <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
        {t('dataset.noWorkspace')}
      </div>
    )
  return <DatasetGrid workspaceSlug={currentSlug} datasetId={datasetId} editable={editable} />
}

/**
 * Bloc BlockNote custom `dataset`.
 *
 * Stocke la référence dans la prop `datasetId`. La (dé)sérialisation markdown
 * (jeton `dataset://<uuid>`) est portée par le codec `lib/blockCodecs/dataset`
 * — même approche que le bloc mermaid.
 */
export const DatasetBlock = createReactBlockSpec(
  {
    type: 'dataset',
    propSchema: {
      datasetId: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <BlockFrame typeLabel="dataset" source={`dataset://${props.block.props.datasetId}`}>
        <DatasetBlockView
          datasetId={props.block.props.datasetId}
          editable={props.editor.isEditable}
        />
      </BlockFrame>
    ),
  },
)
