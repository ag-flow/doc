import type {
  AutomationPrecheck,
  AutomationPrecheckOutcome,
  AutomationPrecheckRule,
} from '../../lib/api'

/** Section « pré-condition » de l'onglet Appel.
 *
 *  Un automate ne savait qu'appeler : il ne pouvait ni vérifier, ni s'abstenir.
 *  D'où deux pannes réelles — recréer un workspace déjà présent (409 en boucle),
 *  et indexer dans un corpus absent (404 jusqu'au dead-letter).
 *
 *  Dans son propre fichier : `AutomationDialog` dépasse déjà largement le plafond
 *  de 300 lignes du dépôt, l'y ajouter aggraverait la dette plutôt que la payer.
 */

const OUTCOMES: { value: AutomationPrecheckOutcome; label: string }[] = [
  { value: 'proceed', label: 'appeler' },
  { value: 'skip', label: 'ne pas appeler' },
  { value: 'defer', label: 'réessayer plus tard' },
]

/** Spécification de départ : la plus courante, « ne recrée pas ce qui existe ». */
export const EMPTY_PRECHECK: AutomationPrecheck = {
  url: '',
  method: 'GET',
  rules: [{ status: [404], then: 'proceed' }],
  default: 'skip',
}

/** « 404, 410 » → [404, 410]. Les entrées non numériques sont ignorées : la
 *  saisie reste libre pendant la frappe sans produire de critère absurde. */
function parseStatuses(raw: string): number[] {
  return raw
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n))
}

function formatStatuses(status: number[] | null | undefined): string {
  return (status ?? []).join(', ')
}

export function PrecheckFields({
  value,
  onChange,
}: {
  value: AutomationPrecheck | null
  onChange: (next: AutomationPrecheck | null) => void
}) {
  const enabled = value !== null

  function patch(partial: Partial<AutomationPrecheck>) {
    if (value === null) return
    onChange({ ...value, ...partial })
  }

  function patchRule(index: number, partial: Partial<AutomationPrecheckRule>) {
    if (value === null) return
    const rules = value.rules.map((r, i) => (i === index ? { ...r, ...partial } : r))
    onChange({ ...value, rules })
  }

  return (
    <div className="rounded border border-rule/[0.6] p-3">
      <label className="flex cursor-pointer items-start gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onChange(e.target.checked ? EMPTY_PRECHECK : null)}
          data-testid="auto-precheck-enable"
        />
        <span>
          <span className="text-[13px] font-[600]">Vérifier avant d’appeler</span>
          <span className="ml-2 text-[12px] text-ink/[0.55]">
            interroge la cible, puis décide d’appeler, de s’abstenir, ou de réessayer plus tard
          </span>
        </span>
      </label>

      {enabled && value !== null && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <div>
              <label className="mb-1 block text-[12px] text-ink/[0.7]">URL de vérification</label>
              <input
                className="input"
                value={value.url}
                onChange={(e) => patch({ url: e.target.value })}
                placeholder="https://…/workspaces/{event.workspaceSlug}-docs"
                data-testid="auto-precheck-url"
              />
              <p className="mt-1 text-[11px] text-ink/[0.55]">
                Mêmes variables que le corps. Une variable non résolue fait échouer l’appel
                plutôt que de partir telle quelle.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-ink/[0.7]">Méthode</label>
              <select
                className="input"
                value={value.method}
                onChange={(e) => patch({ method: e.target.value })}
                data-testid="auto-precheck-method"
              >
                <option value="GET">GET</option>
                <option value="HEAD">HEAD</option>
              </select>
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[12px] text-ink/[0.7]">
                Règles — la première qui correspond l’emporte
              </span>
              <button
                type="button"
                className="cursor-pointer border-0 bg-transparent text-[12px] text-accent-700"
                onClick={() => patch({ rules: [...value.rules, { then: 'proceed' }] })}
                data-testid="auto-precheck-add-rule"
              >
                + règle
              </button>
            </div>

            {value.rules.map((rule, i) => (
              <div key={i} className="mb-2 grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2">
                <input
                  className="input"
                  value={formatStatuses(rule.status)}
                  onChange={(e) => patchRule(i, { status: parseStatuses(e.target.value) })}
                  placeholder="statuts (404)"
                  data-testid={`auto-precheck-rule-status-${i}`}
                />
                <input
                  className="input"
                  value={rule.path ?? ''}
                  onChange={(e) => patchRule(i, { path: e.target.value })}
                  placeholder="chemin (state)"
                  data-testid={`auto-precheck-rule-path-${i}`}
                />
                <input
                  className="input"
                  value={rule.equals ?? ''}
                  onChange={(e) => patchRule(i, { equals: e.target.value })}
                  placeholder="vaut (ready)"
                  data-testid={`auto-precheck-rule-equals-${i}`}
                />
                <select
                  className="input"
                  value={rule.then}
                  onChange={(e) =>
                    patchRule(i, { then: e.target.value as AutomationPrecheckOutcome })
                  }
                  data-testid={`auto-precheck-rule-then-${i}`}
                >
                  {OUTCOMES.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="cursor-pointer border-0 bg-transparent text-ink/[0.55]"
                  onClick={() => patch({ rules: value.rules.filter((_, j) => j !== i) })}
                  data-testid={`auto-precheck-remove-rule-${i}`}
                  aria-label="Retirer la règle"
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div>
            <label className="mb-1 block text-[12px] text-ink/[0.7]">
              Si aucune règle ne correspond
            </label>
            <select
              className="input"
              value={value.default}
              onChange={(e) => patch({ default: e.target.value as AutomationPrecheckOutcome })}
              data-testid="auto-precheck-default"
            >
              {OUTCOMES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-ink/[0.55]">
              Obligatoire : sans issue par défaut, l’appel partirait justement dans les cas
              qu’on cherchait à écarter.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

/** Nettoie la saisie avant envoi : un critère vide ne doit pas être STOCKÉ.
 *
 *  Un `status: []` ou un `path: ""` enregistré se relirait comme un critère posé
 *  que rien ne satisfait — la règle ne matcherait jamais, sans rien dire.
 */
export function cleanPrecheck(value: AutomationPrecheck | null): AutomationPrecheck | null {
  if (value === null) return null
  const rules = value.rules.map((r) => {
    const out: AutomationPrecheckRule = { then: r.then }
    if (r.status && r.status.length > 0) out.status = r.status
    if (r.path) {
      out.path = r.path
      out.equals = r.equals ?? ''
    }
    return out
  })
  return { url: value.url, method: value.method, rules, default: value.default }
}
