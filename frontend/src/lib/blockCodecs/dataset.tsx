/**
 * Codec du bloc dataset : jeton `dataset://<uuid>` ⇆ bloc custom `dataset`.
 *
 * Note spec 39 : le jeton est du contenu déjà en base — supporté tel quel,
 * aucune migration. L'item de menu slash est CONSERVÉ (parité fonctionnelle
 * avec l'existant : « ce lot ne modifie rien fonctionnellement »).
 */
import { Table } from 'lucide-react'
import { DatasetBlock } from '../../components/DatasetBlock'
import { datasetsApi } from '../datasetsApi'
import type { SlashContext, SlashItem } from './index'

export interface DatasetProps extends Record<string, unknown> {
  datasetId: string
}

export const datasetCodec = {
  type: 'dataset',
  pattern:
    /dataset:\/\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g,
  toBlock: (match: RegExpExecArray): DatasetProps => ({ datasetId: match[1] }),
  toMarkdown: (props: DatasetProps): string => `dataset://${props.datasetId ?? ''}`,
  spec: () => DatasetBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('dataset.slashTitle'),
    subtext: ctx.t('dataset.slashHint'),
    onItemClick: () => {
      void (async () => {
        // Crée un dataset vide et insère son bloc à la position courante.
        const slug = `dataset-${crypto.randomUUID().slice(0, 8)}`
        const ds = await datasetsApi.createDataset(ctx.wsSlug, {
          slug,
          label: ctx.t('dataset.defaultLabel'),
        })
        ctx.editor.insertBlocks(
          [{ type: 'dataset', props: { datasetId: ds.id } }],
          ctx.editor.getTextCursorPosition().block,
          'after',
        )
      })()
    },
    aliases: ['dataset', 'tableau', 'table', 'grille', 'données'],
    group: 'Insérer',
    icon: <Table size={18} />,
    key: 'dataset',
  }),
}
