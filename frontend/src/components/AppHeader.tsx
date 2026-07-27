import { Link } from 'react-router-dom'
import { HomeNavPopover } from './HomeNavPopover'
import { Breadcrumb } from './Breadcrumb'

/**
 * En-tête : tête de journal (filet gras puis filet fin), fil d'Ariane à
 * gauche. Il remplace tout titre de page — un écran ne réaffiche pas son nom.
 *
 * Le groupe d'actions de droite de la maquette (recherche globale,
 * notifications) n'est PAS câblé ici : la recherche globale relève de sa
 * propre fiche et les notifications n'ont pas de backend. Aucun bouton mort.
 */
export function AppHeader() {
  return (
    <header className="app-header" data-testid="app-header">
      <div className="header-rule-thick" />
      <div className="header-row">
        <HomeNavPopover />
        <span className="crumb-sep">|</span>
        <Link to="/workspaces" className="header-brand">docflow</Link>
        <span className="crumb-sep">/</span>
        <Breadcrumb />
      </div>
      <div className="header-rule-thin" />
    </header>
  )
}
