/**
 * Fusion three-way du markdown (live-reload phase B) : base commune (version
 * au début de l'édition) / ours (édits utilisateur) / theirs (version backend).
 *
 * Granularité : la ligne — SAUF les blocs fenced (``` … ```) qui sont des
 * tokens ATOMIQUES : un bloc df-x / mermaid / code n'est jamais fusionné ligne à
 * ligne à l'intérieur (arbitrage du cadrage). Un changement identique des deux
 * côtés n'est pas un conflit (excludeFalseConflicts). En zone de conflit,
 * `merged` retient OURS — le compte de conflits déclenche l'UI de résolution.
 */
import { diff3Merge } from 'node-diff3'

/** Découpe en tokens : lignes, sauf blocs fence = un token multi-lignes. */
export function tokenize(md: string): string[] {
  const tokens: string[] = []
  const lines = md.split('\n')
  let i = 0
  while (i < lines.length) {
    if (/^\s*```/.test(lines[i])) {
      const start = i
      i++
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) i++
      if (i < lines.length) i++ // fence fermante incluse
      tokens.push(lines.slice(start, i).join('\n'))
    } else {
      tokens.push(lines[i])
      i++
    }
  }
  return tokens
}

export interface Merge3Result {
  merged: string
  /** Zones en conflit (ours retenu dans `merged`). 0 = fusion propre. */
  conflicts: number
}

export function threeWayMerge(base: string, ours: string, theirs: string): Merge3Result {
  const regions = diff3Merge(tokenize(ours), tokenize(base), tokenize(theirs), {
    excludeFalseConflicts: true,
    stringSeparator: undefined,
  })
  const out: string[] = []
  let conflicts = 0
  for (const region of regions) {
    if (region.ok) {
      out.push(...region.ok)
    } else if (region.conflict) {
      conflicts++
      out.push(...region.conflict.a)
    }
  }
  return { merged: out.join('\n'), conflicts }
}
