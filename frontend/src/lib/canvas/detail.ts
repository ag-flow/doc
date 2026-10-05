/**
 * Paliers de détail au zoom (épic MLD — F6).
 *
 * Un modèle de données dézoomé devient illisible si l'on continue de dessiner
 * chaque champ : le texte se tasse et le coût de rendu explose. On change donc
 * ce qui est affiché par paliers, pas progressivement — un seuil franc est
 * prévisible, là où une interpolation donne un rendu qui « bouge » sans cesse.
 *
 * Conséquence directe sur l'ancrage : sous le palier `fields`, les ports ne sont
 * plus visibles, donc les liens dégradent vers le bord de la boîte
 * (cf. `anchor.ts`). Les deux notions sont liées à dessein.
 */

/** Du plus dézoomé au plus détaillé. */
export type DetailLevel = 'silhouette' | 'title' | 'fields'

/** Seuils de zoom (facteur d'échelle) d'entrée dans chaque palier. */
export const DETAIL_THRESHOLDS: ReadonlyArray<{ min: number; level: DetailLevel }> = [
  { min: 0.75, level: 'fields' },
  { min: 0.4, level: 'title' },
  { min: 0, level: 'silhouette' },
]

export function detailFor(zoom: number): DetailLevel {
  return DETAIL_THRESHOLDS.find((t) => zoom >= t.min)?.level ?? 'silhouette'
}

/** Les ports ne sont accrochables que lorsque les champs sont réellement dessinés. */
export function portsVisibleAt(zoom: number): boolean {
  return detailFor(zoom) === 'fields'
}
