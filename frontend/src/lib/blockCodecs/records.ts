/**
 * Grammaire `records` partagée par les composants d'affichage (spec 40_MCMP).
 *
 * Corps : une ligne = un enregistrement, champs séparés par `|`, espaces
 * autour ignorés, `\|` pour un pipe littéral, lignes vides ignorées.
 * En-tête : optionnelle et EXPLICITE (attribut header="true") — aucune
 * détection heuristique.
 *
 * Attributs de fence : clé="valeur", valeur entre guillemets doubles,
 * `\"` échappé. Parsés ici aussi (partagés par tous les composants).
 */

// ── Attributs de fence ────────────────────────────────────────────────────────

const ATTR_RE = /([A-Za-z_][\w-]*)="((?:[^"\\]|\\.)*)"/g

export interface ParsedAttrs {
  attrs: Record<string, string>
  /** Fragments non reconnus dans l'info string (diagnostic). */
  unknown: string[]
}

/** Parse l'info string d'une fence (après le type) en attributs clé/valeur. */
export function parseAttrs(info: string): ParsedAttrs {
  const attrs: Record<string, string> = {}
  let consumed = ''
  for (const m of info.matchAll(ATTR_RE)) {
    attrs[m[1]] = m[2].replace(/\\(["\\])/g, '$1')
    consumed += m[0] + ' '
  }
  // Tout fragment restant non-blanc est un attribut mal formé.
  let residue = info
  for (const m of info.matchAll(ATTR_RE)) residue = residue.replace(m[0], ' ')
  const unknown = residue
    .split(/\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  return { attrs, unknown }
}

/** Sérialise des attributs en info string canonique (échappe `"` et `\`). */
export function serializeAttrs(attrs: Record<string, string>): string {
  return Object.entries(attrs)
    .map(([k, v]) => ` ${k}="${v.replace(/([\\"])/g, '\\$1')}"`)
    .join('')
}

// ── Corps records ─────────────────────────────────────────────────────────────

export interface RecordsDiagnostic {
  /** Index de ligne DANS LE CORPS (0-based, lignes vides comprises). */
  line: number
  kind: 'extra_fields'
  detail: string
}

export interface ParsedRecords {
  /** Champs de la ligne d'en-tête si header=true, sinon null. */
  header: string[] | null
  /** Lignes de données : champs trimés, complétés à `fields` si fourni. */
  rows: string[][]
  diagnostics: RecordsDiagnostic[]
}

/** Découpe une ligne sur `|` non échappé, puis dé-échappe `\|`. */
function splitFields(line: string): string[] {
  const fields: string[] = []
  let current = ''
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '\\' && line[i + 1] === '|') {
      current += '|'
      i++
    } else if (ch === '|') {
      fields.push(current)
      current = ''
    } else {
      current += ch
    }
  }
  fields.push(current)
  return fields.map((f) => f.trim())
}

/**
 * Parse un corps `records`.
 *
 * @param body   corps brut de la fence
 * @param opts.header  true si la première ligne non vide est un en-tête
 * @param opts.fields  nombre de champs attendus : les manquants sont complétés
 *                     par '', les excédentaires ignorés AVEC diagnostic.
 */
export function parseRecords(
  body: string,
  opts: { header?: boolean; fields?: number } = {},
): ParsedRecords {
  const diagnostics: RecordsDiagnostic[] = []
  let header: string[] | null = null
  const rows: string[][] = []

  const lines = body.split('\n')
  let headerPending = opts.header === true
  lines.forEach((line, i) => {
    if (line.trim().length === 0) return
    let fields = splitFields(line)
    if (opts.fields !== undefined) {
      if (fields.length > opts.fields) {
        diagnostics.push({
          line: i,
          kind: 'extra_fields',
          detail: `${fields.length - opts.fields} champ(s) en excès ignoré(s)`,
        })
        fields = fields.slice(0, opts.fields)
      }
      while (fields.length < opts.fields) fields.push('')
    }
    if (headerPending) {
      header = fields
      headerPending = false
      return
    }
    rows.push(fields)
  })

  return { header, rows, diagnostics }
}

/** Sérialise des lignes en corps records canonique (ré-échappe `|`). */
export function serializeRecords(rows: readonly (readonly string[])[]): string {
  return rows.map((r) => r.map((f) => f.replace(/\|/g, '\\|')).join(' | ')).join('\n')
}
