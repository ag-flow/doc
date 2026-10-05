/**
 * Codec de la puce artefact : une ligne `[label](artifact://<uuid>)` SEULE
 * devient un bloc `artifactChip` (fichier téléchargeable avec icône, taille,
 * type). Un lien `artifact://` au fil du texte n'est PAS revendiqué — il reste
 * un lien cliquable géré par MarkdownViewer (décision de cadrage Q3).
 *
 * L'ancrage `^…$` (drapeau `m`) garantit l'exclusivité de ligne : la présence
 * de tout autre caractère sur la ligne écarte la revendication.
 */
import { Paperclip } from 'lucide-react'
import { ArtifactChipBlock } from '../../components/ArtifactChipBlock'
import { artifactsApi } from '../api'
import type { SlashContext, SlashItem } from './index'

export interface ArtifactChipProps extends Record<string, unknown> {
  id: string
  /** Libellé affiché ; vide = retombe sur le nom de fichier de l'artefact. */
  label: string
}

const UUID =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

/** Ouvre le sélecteur de fichier natif ; résout le fichier choisi (ou null). */
function pickFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.onchange = () => resolve(input.files?.[0] ?? null)
    input.click()
  })
}

export const artifactCodec = {
  type: 'artifactChip',
  // Ligne entière = un lien markdown vers artifact://uuid, rien d'autre.
  pattern: new RegExp(`^[ \\t]*\\[([^\\]\\n]*)\\]\\(artifact://(${UUID})\\)[ \\t]*$`, 'gm'),
  toBlock: (match: RegExpExecArray): ArtifactChipProps => ({
    id: match[2],
    label: match[1] ?? '',
  }),
  toMarkdown: (props: ArtifactChipProps): string =>
    `[${props.label ?? ''}](artifact://${props.id ?? ''})`,
  spec: () => ArtifactChipBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('artifact.slashTitle'),
    subtext: ctx.t('artifact.slashHint'),
    onItemClick: () => {
      void (async () => {
        const file = await pickFile()
        if (!file) return
        try {
          // Upload immédiat (comme une image) : la puce référence l'artefact ;
          // le refcount se cale à l'enregistrement du document.
          const created = await artifactsApi.upload(ctx.wsSlug, file)
          ctx.editor.insertBlocks(
            [{ type: 'artifactChip', props: { id: created.id, label: '' } }],
            ctx.editor.getTextCursorPosition().block,
            'after',
          )
        } catch {
          ctx.onError?.(ctx.t('artifact.uploadError'))
        }
      })()
    },
    aliases: ['fichier', 'file', 'artefact', 'artifact', 'joindre', 'upload', 'téléverser'],
    group: 'Insérer',
    icon: <Paperclip size={18} />,
    key: 'artifact-file',
  }),
}
