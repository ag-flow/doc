/**
 * Codec du bloc maquette d'écran : fence ```df-maquette ⇆ bloc custom
 * `dfMaquette`. Le bloc ne porte PAS le HTML — seulement l'`artifactId` (rendu
 * dans le corps sous forme `artifact://<uuid>`, la SEULE forme comptée au
 * refcount : sans elle, l'artefact de la maquette serait purgé) et des
 * métadonnées d'affichage (titre, viewport, hauteur de repli, description).
 *
 * Une fence sans `artifact://<uuid>` dans son corps n'est PAS revendiquée
 * (return null) — elle reste un bloc de code intact.
 */
import { AppWindow } from '@phosphor-icons/react'
import { MaquetteBlock, type MaquetteProps } from '../../components/MaquetteBlock'
import { parseAttrs, serializeAttrs } from './records'
import type { SlashContext, SlashItem } from './index'

const UUID = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
const ARTIFACT_REF = new RegExp(`artifact://(${UUID})`)

export const maquetteCodec = {
  type: 'dfMaquette',
  pattern: /```df-maquette(?=\s|$)([^\n]*)\n([\s\S]*?)```/g,
  toBlock: (match: RegExpExecArray): MaquetteProps | null => {
    const ref = ARTIFACT_REF.exec(match[2] ?? '')
    if (!ref) return null // pas d'artefact référencé → ce n'est pas une maquette
    const { attrs } = parseAttrs(match[1] ?? '')
    return {
      artifactId: ref[1],
      titre: attrs.titre ?? '',
      viewport: attrs.viewport ?? 'desktop',
      hauteur: attrs.hauteur ?? '',
      description: attrs.description ?? '',
    }
  },
  toMarkdown: (props: MaquetteProps): string => {
    const attrs: Record<string, string> = { viewport: props.viewport || 'desktop' }
    if (props.titre) attrs.titre = props.titre
    if (props.hauteur) attrs.hauteur = props.hauteur
    // description toujours sérialisée : seule surface d'accroche RAG de la maquette.
    attrs.description = props.description ?? ''
    return '```df-maquette' + serializeAttrs(attrs) + '\nartifact://' + props.artifactId + '\n```'
  },
  spec: () => MaquetteBlock(),
  slashItem: (ctx: SlashContext): SlashItem => ({
    title: ctx.t('maquette.slashTitle'),
    subtext: ctx.t('maquette.slashHint'),
    onItemClick: () => {
      // Squelette à compléter : une maquette pointe un artefact HTML mutable
      // existant (créé par un agent via create_artifact mutable .html).
      ctx.editor.insertBlocks(
        [
          {
            type: 'dfMaquette',
            props: { artifactId: '', titre: '', viewport: 'desktop', hauteur: 0, description: '' },
          },
        ],
        ctx.editor.getTextCursorPosition().block,
        'after',
      )
    },
    aliases: ['maquette', 'mockup', 'écran', 'screen', 'wireframe', 'ui'],
    group: 'Insérer',
    icon: <AppWindow size={18} />,
    key: 'df-maquette',
  }),
}
