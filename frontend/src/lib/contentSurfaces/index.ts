/**
 * Registre de surfaces d'affichage par type de contenu (épic MLD — F4).
 *
 * Miroir côté front du registre de codecs du backend (`docflow.codecs`) : le
 * type de contenu d'un document (`DocumentOut.type`) est une CLÉ DE REGISTRE,
 * jamais une condition dans la page. BlockNote cesse d'être « l'éditeur de
 * docflow » pour n'être que la surface du type `md`.
 *
 * La coquille de page (titre, propriétés, commentaires, révisions, export,
 * protocole de sauvegarde) vit AU-DESSUS et ne change pas d'une surface à
 * l'autre — c'est `DocumentShell`.
 *
 * Ajouter un type de contenu = son fichier de surface + une entrée ici.
 * Un type absent du registre retombe sur la surface de repli (texte brut) :
 * jamais de page cassée.
 */

import type { ForwardRefExoticComponent, RefAttributes } from 'react'
import { markdownSurface } from './markdown'
import { plainTextSurface } from './plainText'

// ── Contrat ───────────────────────────────────────────────────────────────────

export interface ContentEditorProps {
  /** Corps du document au montage. La surface est NON CONTRÔLÉE : elle ne relit
   *  pas cette prop ensuite (la page force un remontage via `key`). */
  initialContent: string
  /** Signale une modification locale. Sans argument : la page n'apprend le
   *  contenu courant qu'au moment de la sauvegarde, via `getContent()`. */
  onDirty: () => void
  /** Workspace courant — upload d'artefacts, recherche de documents liés. */
  wsSlug?: string
}

export interface ContentEditorHandle {
  /** Contenu courant sérialisé pour la persistance (ce qui part en base). */
  getContent: () => Promise<string>
}

export interface ContentViewerProps {
  content: string
  /** Rendu sans cadre (bordure / fond) — pour la lecture prose « wiki ». */
  bare?: boolean
}

export interface ContentViewerHandle {
  /** Copie riche (HTML + composants en images). Optionnelle : toutes les
   *  surfaces n'ont pas de représentation riche à mettre au presse-papiers. */
  copyRich?: () => Promise<void>
}

export type ContentEditorComponent = ForwardRefExoticComponent<
  ContentEditorProps & RefAttributes<ContentEditorHandle>
>

export type ContentViewerComponent = ForwardRefExoticComponent<
  ContentViewerProps & RefAttributes<ContentViewerHandle>
>

export interface ContentSurface {
  /** Valeur de `DocumentOut.type` servie par cette surface. Unique dans le registre. */
  contentType: string
  Editor: ContentEditorComponent
  Viewer: ContentViewerComponent
  /** La surface sait produire une copie riche (HTML + composants en images).
   *  Déclaratif : la page doit décider d'afficher l'action AVANT le montage,
   *  quand la `ref` est encore nulle. Défaut : non. */
  supportsRichCopy?: boolean
}

// ── Registre ──────────────────────────────────────────────────────────────────

/** Surface de repli de tout type inconnu. */
export const FALLBACK_SURFACE: ContentSurface = plainTextSurface

export const SURFACES: Record<string, ContentSurface> = {
  [markdownSurface.contentType]: markdownSurface,
}

/** Surface servant ce type de contenu, ou le repli si le type est inconnu. */
export function surfaceFor(contentType: string | null | undefined): ContentSurface {
  if (!contentType) return FALLBACK_SURFACE
  return SURFACES[contentType] ?? FALLBACK_SURFACE
}

export { markdownSurface, plainTextSurface }
