import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MagnifyingGlass } from '@phosphor-icons/react'
import { HomeNavPopover } from './HomeNavPopover'
import { Breadcrumb } from './Breadcrumb'
import { CommandPalette } from './CommandPalette'
import { useHeaderSlot } from './HeaderSlot'

/**
 * En-tête : tête de journal (filet gras puis filet fin), fil d'Ariane à
 * gauche, recherche globale à droite (loupe ou Cmd/Ctrl+K).
 *
 * Les notifications de la maquette ne sont PAS câblées : aucun backend —
 * pas de bouton mort.
 */
export function AppHeader() {
  const [searchOpen, setSearchOpen] = useState(false)
  const { setEl, occupied } = useHeaderSlot()
  // Le focus revient à l'élément qui a ouvert la palette (DoD) : loupe ou
  // élément actif au moment du raccourci clavier.
  const openerRef = useRef<HTMLElement | null>(null)

  function openSearch() {
    openerRef.current = document.activeElement as HTMLElement | null
    setSearchOpen(true)
  }

  function closeSearch() {
    setSearchOpen(false)
    openerRef.current?.focus()
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (searchOpen) closeSearch()
        else openSearch()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchOpen])

  return (
    <header className="app-header" data-testid="app-header">
      <div className="header-rule-thick" />
      <div className="header-row">
        <HomeNavPopover />
        <span className="crumb-sep">|</span>
        <Link to="/workspaces" className="header-brand">docflow</Link>
        <span className="crumb-sep">/</span>
        <Breadcrumb />
        <span className="flex-1" />
        {/* Actions contextuelles de la page (document…) — sur la ligne du fil
            d'Ariane, comme la maquette. */}
        <span
          ref={setEl}
          className="flex shrink-0 items-center gap-1.5"
          data-testid="header-actions-slot"
        />
        {!occupied && (
          <button
            type="button"
            className="header-icon flex items-center gap-1.5 text-[13px]"
            onClick={openSearch}
            title="Rechercher (Ctrl+K)"
            data-testid="open-search-btn"
          >
            <MagnifyingGlass size={16} weight="duotone" />
            Rechercher
          </button>
        )}
      </div>
      <div className="header-rule-thin" />

      {searchOpen && <CommandPalette onClose={closeSearch} />}
    </header>
  )
}
