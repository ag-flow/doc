import type { BlockQueryBody, FilterClause, QueryOperator, SortKey } from './api'

/**
 * Sérialisation du QuerySpec dans l'URL : un tri et un filtrage doivent être
 * partageables et survivre au rechargement (DoD écran Documents).
 *
 * Forme compacte et lisible dans la barre d'adresse :
 *   ?sort=statut:asc,titre:desc
 *   &f=statut:in:en_cours|fait&f=poids:between:3|8
 *   &page=2&vue=liste
 *
 * `:` sépare les parties d'une clause, `|` les valeurs multiples. Les deux sont
 * échappés dans les valeurs (`~c` / `~p`, `~` lui-même en `~t`) : un statut
 * nommé « a:b » ou un texte contenant un pipe ne doit pas casser le parsing.
 */

const ESCAPES: [string, string][] = [['~', '~t'], [':', '~c'], ['|', '~p'], [',', '~m']]

function esc(v: string): string {
  return ESCAPES.reduce((acc, [from, to]) => acc.split(from).join(to), v)
}

function unesc(v: string): string {
  // Inverse dans l'ordre inverse — `~t` en dernier, sinon il réintroduirait des `~`.
  return [...ESCAPES].reverse().reduce((acc, [from, to]) => acc.split(to).join(from), v)
}

const OPERATORS: QueryOperator[] = [
  'eq', 'contains', 'starts_with', 'lt', 'gt', 'between', 'before', 'after', 'in',
]

function clauseToParam(f: FilterClause): string {
  const values = f.values ?? (f.value !== undefined && f.value !== null ? [f.value] : [])
  return [esc(f.prop), f.op, values.map(esc).join('|')].join(':')
}

function paramToClause(raw: string): FilterClause | null {
  const parts = raw.split(':')
  if (parts.length < 3) return null
  const [prop, op] = parts
  if (!prop || !OPERATORS.includes(op as QueryOperator)) return null
  // La valeur peut contenir des ':' échappés, mais jamais bruts : on rejoint le reste.
  const values = parts.slice(2).join(':').split('|').filter((v) => v !== '').map(unesc)
  if (values.length === 0) return null
  const clause: FilterClause = { prop: unesc(prop), op: op as QueryOperator }
  if (op === 'in' || op === 'between') clause.values = values
  else clause.value = values[0]
  return clause
}

export interface UrlState {
  spec: Pick<BlockQueryBody, 'filters' | 'sort' | 'page'>
  /** Vue arbre (défaut) ou liste plate, en mode navigation. */
  treeMode: boolean
}

/** Params d'URL → état. Tout paramètre illisible est ignoré : une URL tronquée
 *  ou bricolée à la main dégrade vers l'état par défaut, elle ne casse pas. */
export function readUrlState(params: URLSearchParams): UrlState {
  const sort: SortKey[] = (params.get('sort') ?? '')
    .split(',')
    .filter(Boolean)
    .map((chunk) => {
      const [key, dir] = chunk.split(':')
      return key ? { key: unesc(key), dir: dir === 'desc' ? 'desc' : 'asc' } as SortKey : null
    })
    .filter((s): s is SortKey => s !== null)

  const filters = params.getAll('f')
    .map(paramToClause)
    .filter((c): c is FilterClause => c !== null)

  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1)

  return { spec: { filters, sort, page }, treeMode: params.get('vue') !== 'liste' }
}

/** État → params d'URL. Les valeurs par défaut ne sont PAS écrites : l'URL d'un
 *  écran vierge reste nue. */
export function writeUrlState(state: UrlState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.spec.sort.length > 0) {
    params.set('sort', state.spec.sort.map((s) => `${esc(s.key)}:${s.dir}`).join(','))
  }
  for (const f of state.spec.filters) params.append('f', clauseToParam(f))
  if (state.spec.page > 1) params.set('page', String(state.spec.page))
  if (!state.treeMode) params.set('vue', 'liste')
  return params
}
