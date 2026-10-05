/**
 * Grammaire `outline` — corps indenté → arbre, pour les diagrammes hiérarchiques
 * (Nested, Tree). Une ligne = un nœud ; l'indentation donne la profondeur.
 *
 * Unité d'indentation : un TAB = un niveau ; sinon 2 espaces = un niveau. Le
 * libellé peut porter une note après un `|` (« label | note »). Lignes vides
 * ignorées. Un saut de profondeur (enfant sans parent au bon niveau) est
 * rattaché au niveau disponible le plus proche (jamais d'erreur silencieuse).
 */

export interface OutlineNode {
  label: string
  note?: string
  children: OutlineNode[]
}

export interface ParsedOutline {
  roots: OutlineNode[]
  /** Lignes non vides sans libellé (ignorées). */
  ignored: number
}

/** Profondeur d'indentation d'une ligne (tab = 1 niveau, 2 espaces = 1 niveau). */
function indentDepth(line: string): number {
  let spaces = 0
  for (const ch of line) {
    if (ch === '\t') spaces += 2
    else if (ch === ' ') spaces += 1
    else break
  }
  return Math.floor(spaces / 2)
}

/** Sépare « label | note » (premier `|` seulement). */
function splitLabel(text: string): { label: string; note?: string } {
  const i = text.indexOf('|')
  if (i === -1) return { label: text.trim() }
  const note = text.slice(i + 1).trim()
  return { label: text.slice(0, i).trim(), note: note.length > 0 ? note : undefined }
}

/** Parse un corps indenté en forêt de nœuds. */
export function parseOutline(body: string): ParsedOutline {
  const roots: OutlineNode[] = []
  let ignored = 0
  // Pile des ancêtres courants, indexée par profondeur effective.
  const stack: { depth: number; node: OutlineNode }[] = []

  for (const raw of body.split('\n')) {
    if (raw.trim().length === 0) continue
    const depth = indentDepth(raw)
    const { label, note } = splitLabel(raw.trim())
    if (label.length === 0) {
      ignored++
      continue
    }
    const node: OutlineNode = { label, note, children: [] }
    // Remonte la pile jusqu'à un parent de profondeur strictement inférieure.
    while (stack.length > 0 && stack[stack.length - 1].depth >= depth) stack.pop()
    if (stack.length === 0) roots.push(node)
    else stack[stack.length - 1].node.children.push(node)
    stack.push({ depth, node })
  }

  return { roots, ignored }
}

/** Nombre total de nœuds d'une forêt. */
export function countNodes(nodes: OutlineNode[]): number {
  return nodes.reduce((n, node) => n + 1 + countNodes(node.children), 0)
}

/** Profondeur maximale d'une forêt (1 pour une forêt de feuilles). */
export function maxDepth(nodes: OutlineNode[]): number {
  return nodes.reduce((d, node) => Math.max(d, 1 + (node.children.length ? maxDepth(node.children) : 0)), 0)
}
