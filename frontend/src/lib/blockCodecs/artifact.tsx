/**
 * Codec de la puce artefact : une ligne `[label](artifact://<uuid>)` SEULE
 * devient un bloc `artifactChip` (fichier téléchargeable avec icône, taille,
 * type). Un lien `artifact://` au fil du texte n'est PAS revendiqué — il reste
 * un lien cliquable géré par MarkdownViewer (décision de cadrage Q3).
 *
 * L'ancrage `^…$` (drapeau `m`) garantit l'exclusivité de ligne : la présence
 * de tout autre caractère sur la ligne écarte la revendication.
 */
import { ArtifactChipBlock } from '../../components/ArtifactChipBlock'

export interface ArtifactChipProps extends Record<string, unknown> {
  id: string
  /** Libellé affiché ; vide = retombe sur le nom de fichier de l'artefact. */
  label: string
}

const UUID =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

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
}
