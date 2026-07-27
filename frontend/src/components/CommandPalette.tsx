import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useMatch } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, docsApi, referencesApi, type DataBlockOut, type DocumentSearchResult, type WorkspaceOut } from '../lib/api'

interface PaletteItem {
  group: string
  label: string
  hint?: string
  path: string
}

/** Surligne la correspondance en cyan — la raison pour laquelle un résultat
 *  matche doit se voir. */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase()
  if (!q) return <>{text}</>
  const i = text.toLowerCase().indexOf(q)
  if (i < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, i)}
      <mark className="bg-accent-200 text-inherit">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  )
}

/**
 * Palette de recherche globale : loupe de l'en-tête ou Cmd/Ctrl+K. Résultats
 * groupés (documents, blocs, workspaces, actions), navigation clavier, Échap
 * pour fermer — le focus revient au déclencheur (géré par l'appelant qui a
 * capturé `document.activeElement`).
 */
export function CommandPalette({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const wsSlug = useMatch('/ws/:wsSlug/*')?.params.wsSlug ?? null
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => inputRef.current?.focus(), [])

  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    staleTime: 60_000,
  })
  const { data: blocks = [] } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug!),
    enabled: Boolean(wsSlug),
    staleTime: 60_000,
  })
  // Documents : recherche serveur dans le workspace courant uniquement (il n'y
  // a pas d'index cross-workspace) — hors workspace, le groupe est absent.
  const { data: docs = [] } = useQuery<DocumentSearchResult[]>({
    queryKey: ['palette-docs', wsSlug, query],
    queryFn: () => referencesApi.searchDocuments(wsSlug!, query.trim(), 8),
    enabled: Boolean(wsSlug) && query.trim().length >= 2,
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  })

  const items = useMemo<PaletteItem[]>(() => {
    const q = query.trim().toLowerCase()
    const out: PaletteItem[] = []
    for (const d of docs) {
      // `bloc` = slug du bloc porteur (résultat serveur).
      const block = blocks.find((b) => b.slug === d.bloc)
      if (!d.bloc) continue
      out.push({
        group: 'Documents',
        label: d.title,
        hint: block ? `${wsSlug} › ${block.label}` : wsSlug ?? undefined,
        path: `/ws/${wsSlug}/blocs/${d.bloc}/documents/${d.id}`,
      })
    }
    for (const b of blocks) {
      if (q && !b.label.toLowerCase().includes(q) && !b.slug.includes(q)) continue
      out.push({
        group: 'Blocs',
        label: b.label,
        hint: b.functional_type_slug,
        path: `/ws/${wsSlug}/blocs/${b.slug}/documents`,
      })
    }
    for (const w of workspaces) {
      if (q && !w.label.toLowerCase().includes(q) && !w.slug.includes(q)) continue
      out.push({ group: 'Workspaces', label: w.label, hint: w.slug, path: `/ws/${w.slug}/blocs` })
    }
    const actions: PaletteItem[] = [
      { group: 'Actions', label: 'Tous les workspaces', path: '/workspaces' },
      { group: 'Actions', label: 'Mon profil', path: '/me' },
      { group: 'Actions', label: 'Templates', path: '/templates' },
      { group: 'Actions', label: 'Contrats OpenAPI', path: '/contracts' },
      ...(wsSlug
        ? [
            { group: 'Actions', label: 'Automates du workspace', path: `/ws/${wsSlug}/automations` },
            { group: 'Actions', label: 'Types fonctionnels', path: `/ws/${wsSlug}/types` },
          ]
        : []),
    ]
    for (const a of actions) {
      if (q && !a.label.toLowerCase().includes(q)) continue
      out.push(a)
    }
    return out.slice(0, 24)
  }, [query, docs, blocks, workspaces, wsSlug])

  // La sélection reste dans la liste quand les résultats changent.
  useEffect(() => {
    if (active >= items.length) setActive(Math.max(0, items.length - 1))
  }, [items.length, active])

  function go(item: PaletteItem) {
    onClose()
    void navigate(item.path)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter' && items[active]) {
      e.preventDefault()
      go(items[active])
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  let lastGroup = ''

  return (
    <div className="dialog-backdrop z-[90] !place-items-start !pt-[12vh]" onClick={onClose}>
      <div
        className="dialog w-full !max-w-xl !gap-0 !p-0"
        role="dialog"
        aria-modal="true"
        aria-label="Recherche"
        onClick={(e) => e.stopPropagation()}
        data-testid="command-palette"
      >
        {/* Champ en grand sérif, sans cadre : la palette EST le champ. */}
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setActive(0) }}
          onKeyDown={onKeyDown}
          placeholder="Rechercher…"
          className="w-full border-0 bg-transparent px-5 py-4 text-[22px] outline-none
            [font-family:var(--font-heading)] placeholder:text-ink/[0.35]"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-results"
          aria-activedescendant={items[active] ? `palette-item-${active}` : undefined}
          data-testid="palette-input"
        />
        <div className="h-px bg-[var(--color-divider)]" />

        <ul
          id="palette-results"
          role="listbox"
          className="dialog-scroll m-0 max-h-[50vh] list-none overflow-y-auto p-2"
          data-testid="palette-results"
        >
          {items.length === 0 ? (
            /* DoD : un état vide qui se nomme, jamais une liste blanche. */
            <li className="px-3 py-6 text-center text-[14px] text-ink/[0.55]" data-testid="palette-empty">
              {query.trim()
                ? `Aucun résultat pour « ${query.trim()} ».`
                : 'Tapez pour chercher documents, blocs, workspaces et actions.'}
            </li>
          ) : (
            items.map((item, i) => {
              const showGroup = item.group !== lastGroup
              lastGroup = item.group
              return (
                <li key={`${item.group}-${item.path}-${item.label}`}>
                  {showGroup && (
                    <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.1em] text-ink/[0.45]">
                      {item.group}
                    </div>
                  )}
                  <button
                    type="button"
                    id={`palette-item-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => go(item)}
                    className={`flex w-full items-baseline gap-2 rounded-sm border-0 px-3 py-1.5
                      text-left text-[15px] ${i === active ? 'bg-accent-100' : 'bg-transparent'}`}
                    data-testid={`palette-item-${i}`}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      <Highlight text={item.label} query={query} />
                    </span>
                    {item.hint && (
                      <span className="shrink-0 text-[11px] text-ink/[0.45]">{item.hint}</span>
                    )}
                  </button>
                </li>
              )
            })
          )}
        </ul>
      </div>
    </div>
  )
}
