/** Registre de glyphes d'icônes (noyau ~12, catalogue extensible).
 *
 *  Chaque glyphe est un fragment SVG dessiné sur un viewBox 0 0 24 24, en
 *  trait `currentColor` (hérite de la couleur du contexte). Le style de trait
 *  (fill:none, stroke:currentColor, largeur, jointures) est porté par <Icon>,
 *  donc les glyphes ne portent QUE la géométrie ; `fill="currentColor"` n'est
 *  posé que sur les aplats pleins (points, pastilles).
 *
 *  Le noyau couvre les besoins Architecture (Lot 2) / Sequence (Lot 5). Le
 *  catalogue complet (~55) est une tâche de contenu dédiée. */
import type { ReactElement } from 'react'

export const ICONS: Record<string, ReactElement> = {
  laptop: (
    <>
      <rect x="4" y="5" width="16" height="11" rx="1.5" />
      <path d="M2 19h20" />
    </>
  ),
  server: (
    <>
      <rect x="4" y="4" width="16" height="7" rx="1.5" />
      <rect x="4" y="13" width="16" height="7" rx="1.5" />
      <circle cx="8" cy="7.5" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="8" cy="16.5" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" />
    </>
  ),
  postgres: (
    // Base de données « pg » : cylindre + monogramme mono discret.
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <text x="12" y="15" fontSize="6" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="monospace">pg</text>
    </>
  ),
  docker: (
    // Empilement de conteneurs + ligne d'eau ondulée.
    <>
      <rect x="4" y="11" width="3" height="3" />
      <rect x="8" y="11" width="3" height="3" />
      <rect x="12" y="11" width="3" height="3" />
      <rect x="8" y="7" width="3" height="3" />
      <path d="M3 15c2 1.5 5 1.5 8 1 3-.5 5-2 6-4" />
    </>
  ),
  kubernetes: (
    // Barre (helm) : heptagone + moyeu + rayons.
    <>
      <path d="M12 3l7 4v6l-7 4-7-4V7z" />
      <circle cx="12" cy="10.5" r="2" />
      <path d="M12 3v5M19 7l-5 3.5M5 7l5 3.5M8.5 16.5l1.5-4M15.5 16.5l-1.5-4" />
    </>
  ),
  cloud: (
    <path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.5A3.5 3.5 0 0 1 17 18z" />
  ),
  github: (
    // Chat stylisé dans un cercle (silhouette monochrome simplifiée).
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 6.5l1.5 2M16 6.5l-1.5 2" />
      <circle cx="9.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <path d="M9 16c1 1 5 1 6 0" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </>
  ),
  api: (
    // Accolades { } encadrant un point : contrat d'API.
    <>
      <path d="M8 5c-2 0-2 2-2 3.5S5 12 4 12c1 0 2 0 2 3.5S6 19 8 19" />
      <path d="M16 5c2 0 2 2 2 3.5S19 12 20 12c-1 0-2 0-2 3.5S18 19 16 19" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  queue: (
    // File : maillons alignés + flèche de sortie.
    <>
      <rect x="3" y="9" width="4" height="6" rx="1" />
      <rect x="9" y="9" width="4" height="6" rx="1" />
      <rect x="15" y="9" width="4" height="6" rx="1" />
      <path d="M20 12h2M21 10l1 2-1 2" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
    </>
  ),
}

/** Noms d'icônes disponibles dans le noyau. */
export const ICON_NAMES = Object.keys(ICONS) as IconName[]

export type IconName = keyof typeof ICONS
