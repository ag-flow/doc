/**
 * Analyse CSV côté client (papaparse) + inférence de type par colonne.
 *
 * Miroir de la logique d'import backend (`datasets/csv_io.py`) : type le plus
 * spécifique acceptant TOUTES les valeurs non vides (ordre int → float → date →
 * bool → url), sinon `text`. Les slugs de colonne sont dérivés des en-têtes et
 * dédoublonnés. Ce module est pur et testable (l'aperçu d'import le réutilise).
 */
import Papa from 'papaparse'
import type { DatasetColumnType } from './datasetsApi'

/** Colonne inférée présentée dans l'aperçu d'import (type éditable ensuite). */
export interface InferredColumn {
  slug: string
  label: string
  type: DatasetColumnType
}

export interface ParsedCsv {
  columns: InferredColumn[]
  /** Lignes de données (hors en-tête), chaque cellule alignée sur `columns`. */
  rows: string[][]
}

const URL_RE = /^https?:\/\/\S+$/
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const BOOL_VALUES = new Set(['true', 'false', '1', '0', 'yes', 'no', 'oui', 'non'])

/** Ordre d'inférence — miroir de `_INFER_ORDER` + `url` (backend). */
const INFER_ORDER: DatasetColumnType[] = ['int', 'float', 'date', 'bool', 'url']

function isConvertible(type: DatasetColumnType, raw: string): boolean {
  const v = raw.trim()
  switch (type) {
    case 'int':
      return /^[+-]?\d+$/.test(v)
    case 'float':
      return v !== '' && Number.isFinite(Number(v))
    case 'date':
      return DATE_RE.test(v)
    case 'bool':
      return BOOL_VALUES.has(v.toLowerCase())
    case 'url':
      return URL_RE.test(v)
    default:
      return true
  }
}

/** Type le plus spécifique acceptant toutes les valeurs non vides, sinon `text`. */
export function inferColumnType(values: string[]): DatasetColumnType {
  const nonEmpty = values.filter((v) => v != null && v.trim() !== '')
  if (nonEmpty.length === 0) return 'text'
  for (const candidate of INFER_ORDER) {
    if (nonEmpty.every((v) => isConvertible(candidate, v))) return candidate
  }
  return 'text'
}

/** Réduit un en-tête en slug valide (`^[a-z0-9][a-z0-9_-]*`, ≤100). */
export function slugifyHeader(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 100)
    .replace(/^-+|-+$/g, '')
  return slug || 'col'
}

/** Rend `slug` unique dans `used` (suffixe `-2`, `-3`…) et l'y ajoute. */
function dedup(slug: string, used: Set<string>): string {
  let candidate = slug
  let n = 2
  while (used.has(candidate)) {
    candidate = `${slug}-${n}`
    n += 1
  }
  used.add(candidate)
  return candidate
}

/**
 * Parse un texte CSV et infère les colonnes.
 *
 * @param hasHeader la première ligne porte les en-têtes (sinon `col-1`, `col-2`…).
 */
export function parseCsv(csvText: string, hasHeader = true): ParsedCsv {
  const parsed = Papa.parse<string[]>(csvText, { skipEmptyLines: 'greedy' })
  const rows = parsed.data.filter((r) => Array.isArray(r) && r.some((c) => (c ?? '').trim() !== ''))
  if (rows.length === 0) return { columns: [], rows: [] }

  const width = rows.reduce((max, r) => Math.max(max, r.length), 0)
  const headerRow = hasHeader ? rows[0] : null
  const dataRows = hasHeader ? rows.slice(1) : rows

  const used = new Set<string>()
  const columns: InferredColumn[] = []
  for (let i = 0; i < width; i += 1) {
    const label = headerRow?.[i]?.trim() || `col-${i + 1}`
    const slug = dedup(slugifyHeader(label), used)
    const columnValues = dataRows.map((r) => r[i] ?? '')
    columns.push({ slug, label, type: inferColumnType(columnValues) })
  }

  const normalizedRows = dataRows.map((r) =>
    Array.from({ length: width }, (_, i) => r[i] ?? ''),
  )
  return { columns, rows: normalizedRows }
}
