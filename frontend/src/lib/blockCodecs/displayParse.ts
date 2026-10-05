/**
 * Parsing/validation du corps `df-display` (spec A2UI simplifiée, ADR
 * 5713844b) : adjacency list JSON plate → arbre de rendu + diagnostics.
 *
 * Règle d'or (commune aux blocs custom) : JAMAIS d'échec de rendu — tout ce
 * qui est valide s'affiche, le reste est ignoré et compté dans les
 * diagnostics.
 */
import { z } from 'zod'

export const MAX_COMPONENTS = 500
export const MAX_DEPTH = 32

const componentSchema = z
  .object({
    id: z.string().min(1),
    component: z.string().min(1),
    children: z.array(z.string()).optional(),
  })
  .passthrough()

export interface DisplayComponent {
  id: string
  component: string
  children?: string[]
  [key: string]: unknown
}

/** Nœud d'arbre prêt à rendre (les refs par id sont résolues). */
export interface DisplayNode {
  id: string
  component: string
  props: Record<string, unknown>
  children: DisplayNode[]
}

export interface DisplayDiagnostics {
  /** Entrées invalides (pas un objet {id, component} conforme). */
  invalid: number
  /** ids en doublon (le premier gagne). */
  duplicates: number
  /** Composants jamais atteints depuis la racine. */
  orphans: number
  /** Coupes de garde : cycle détecté, profondeur ou budget dépassés. */
  cut: number
  /** Références d'enfant vers un id inconnu. */
  brokenRefs: number
}

export interface ParsedDisplay {
  root: DisplayNode | null
  diagnostics: DisplayDiagnostics
}

/** Corps candidat : un tableau JSON non vide (sert au rejet de l'alias
 *  ```display — un corps non conforme laisse le bloc en code ordinaire). */
export function isDisplayBody(raw: string): boolean {
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

export function parseDisplay(raw: string): ParsedDisplay {
  const diagnostics: DisplayDiagnostics = {
    invalid: 0,
    duplicates: 0,
    orphans: 0,
    cut: 0,
    brokenRefs: 0,
  }
  let entries: unknown[]
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return { root: null, diagnostics }
    entries = parsed
  } catch {
    return { root: null, diagnostics }
  }

  const byId = new Map<string, DisplayComponent>()
  for (const entry of entries) {
    const r = componentSchema.safeParse(entry)
    if (!r.success) {
      diagnostics.invalid++
      continue
    }
    if (byId.has(r.data.id)) {
      diagnostics.duplicates++
      continue
    }
    byId.set(r.data.id, r.data as DisplayComponent)
  }
  if (byId.size === 0) return { root: null, diagnostics }

  // Racine : id "root" sinon premier composant valide (ADR).
  const rootId = byId.has('root') ? 'root' : [...byId.keys()][0]

  const reached = new Set<string>()
  let budget = MAX_COMPONENTS

  const build = (id: string, path: Set<string>, depth: number): DisplayNode | null => {
    const comp = byId.get(id)
    if (comp === undefined) {
      diagnostics.brokenRefs++
      return null
    }
    if (path.has(id) || depth > MAX_DEPTH || budget <= 0) {
      diagnostics.cut++
      return null
    }
    budget--
    reached.add(id)
    const { id: _id, component, children, ...props } = comp
    const nextPath = new Set(path).add(id)
    const childNodes = (children ?? [])
      .map((c) => build(c, nextPath, depth + 1))
      .filter((n): n is DisplayNode => n !== null)
    return { id, component, props, children: childNodes }
  }

  const root = build(rootId, new Set(), 1)
  diagnostics.orphans = byId.size - reached.size
  return { root, diagnostics }
}
