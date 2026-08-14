/** Variante sketchy — filtre SVG turbulence/déplacement pour un rendu « dessiné
 *  à la main ». Poser <SketchyDefs/> une fois dans le <svg>, puis appliquer
 *  `filter={sketchy()}` sur un <g> à esquisser. */

export const SKETCHY_FILTER_ID = 'df-sketchy'

export interface SketchyDefsProps {
  /** Id du filtre (unique si plusieurs intensités coexistent). */
  id?: string
  /** Intensité du tremblé (déplacement en px). Défaut 2. */
  roughness?: number
  /** Graine du bruit (déterministe pour un rendu stable). Défaut 7. */
  seed?: number
}

/** Déclare le filtre sketchy dans les <defs> du SVG courant. */
export function SketchyDefs({ id = SKETCHY_FILTER_ID, roughness = 2, seed = 7 }: SketchyDefsProps) {
  return (
    <defs>
      <filter id={id} data-diagram="sketchy-filter" x="-10%" y="-10%" width="120%" height="120%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.02 0.03"
          numOctaves={2}
          seed={seed}
          result="noise"
        />
        <feDisplacementMap in="SourceGraphic" in2="noise" scale={roughness} xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </defs>
  )
}

/** Référence `filter` à appliquer sur un élément. */
export function sketchy(id: string = SKETCHY_FILTER_ID): string {
  return `url(#${id})`
}
