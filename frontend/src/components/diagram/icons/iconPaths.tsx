/** Catalogue de glyphes d'icônes IT/cloud (66 — cible de 55 dépassée).
 *
 *  Chaque glyphe est un fragment SVG dessiné sur un viewBox 0 0 24 24, en
 *  trait `currentColor` (hérite de la couleur du contexte). Le style de trait
 *  (fill:none, stroke:currentColor, largeur, jointures) est porté par <Icon>,
 *  donc les glyphes ne portent QUE la géométrie ; `fill="currentColor"` n'est
 *  posé que sur les aplats pleins (points, pastilles).
 *
 *  Les marques (AWS, Azure, GCP, Docker, Kubernetes, GitHub, Postgres, Kafka…)
 *  sont des ÉVOCATIONS monochromes au trait, pas des reproductions de logo :
 *  un logo officiel est une œuvre déposée, et son détail est illisible à 16 px.
 *  On garde la silhouette reconnaissable, dans le style du reste du catalogue. */
import type { ReactElement } from 'react'

export const ICONS: Record<string, ReactElement> = {
  // ── Postes & terminaux ──────────────────────────────────────────────────
  laptop: (
    <>
      <rect x="4" y="5" width="16" height="11" rx="1.5" />
      <path d="M2 19h20" />
    </>
  ),
  desktop: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="1.5" />
      <path d="M9 20h6M12 16v4" />
    </>
  ),
  mobile: (
    <>
      <rect x="7" y="2.5" width="10" height="19" rx="2" />
      <path d="M10.5 5.5h3" />
      <circle cx="12" cy="18.5" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  browser: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <path d="M3 9h18" />
      <circle cx="6" cy="6.5" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8.6" cy="6.5" r="0.8" fill="currentColor" stroke="none" />
    </>
  ),
  terminal: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <path d="M7 9l3 3-3 3M13 15h4" />
    </>
  ),
  iot: (
    <>
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
      <path d="M10 4v3M14 4v3M10 17v3M14 17v3M4 10h3M4 14h3M17 10h3M17 14h3" />
    </>
  ),

  // ── Serveurs & exécution ────────────────────────────────────────────────
  server: (
    <>
      <rect x="4" y="4" width="16" height="7" rx="1.5" />
      <rect x="4" y="13" width="16" height="7" rx="1.5" />
      <circle cx="8" cy="7.5" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="8" cy="16.5" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  vm: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <rect x="7" y="9" width="10" height="6" rx="1" />
    </>
  ),
  container: (
    <>
      <rect x="4" y="7" width="16" height="10" rx="1" />
      <path d="M8 7v10M12 7v10M16 7v10" />
    </>
  ),
  pod: (
    <>
      <path d="M12 3l7.5 4.3v8.6L12 20.2 4.5 15.9V7.3z" />
      <circle cx="12" cy="11.6" r="2.4" />
    </>
  ),
  cpu: (
    <>
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <rect x="10" y="10" width="4" height="4" />
      <path d="M10 4v3M14 4v3M10 17v3M14 17v3M4 10h3M4 14h3M17 10h3M17 14h3" />
    </>
  ),
  serverless: (
    // Éclair : exécution à la demande, sans serveur géré.
    <path d="M13 3L5 13h5l-1 8 8-10h-5z" />
  ),
  cluster: (
    <>
      <circle cx="12" cy="5.5" r="2.5" />
      <circle cx="5.5" cy="17" r="2.5" />
      <circle cx="18.5" cy="17" r="2.5" />
      <path d="M10.4 7.4L7 14.6M13.6 7.4L17 14.6M8 17h8" />
    </>
  ),

  // ── Fournisseurs cloud ──────────────────────────────────────────────────
  cloud: <path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1.5A3.5 3.5 0 0 1 17 18z" />,
  aws: (
    // Nuage + arc « sourire » ascendant, signature visuelle de la marque.
    <>
      <path d="M6 12a3.2 3.2 0 0 1 .6-6.3A4.2 4.2 0 0 1 14.6 6 2.9 2.9 0 0 1 15 12z" />
      <path d="M3 17c4.5 2.6 13.5 2.6 18 0" />
      <path d="M19 15.4l2 1.6-2 1.6" />
    </>
  ),
  azure: (
    // Deux voiles triangulaires, silhouette du « A ».
    <>
      <path d="M9.5 4L3 18h5l4-11z" />
      <path d="M12.5 8L21 18H9l3-4h3z" />
    </>
  ),
  gcp: (
    // Hexagone (compute) + arc orbital.
    <>
      <path d="M12 4l6.9 4v8L12 20l-6.9-4V8z" />
      <path d="M8.5 12a3.5 3.5 0 0 0 6.2 2.2" />
      <path d="M15.5 12a3.5 3.5 0 0 0-6.2-2.2" />
    </>
  ),

  // ── Données & stockage ──────────────────────────────────────────────────
  database: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" />
    </>
  ),
  postgres: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <text x="12" y="15" fontSize="6" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="monospace">pg</text>
    </>
  ),
  mysql: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <path d="M7 13c1.5 2.5 3 3.5 5 3.5" />
      <path d="M14 14.5l2.5 2M16.5 16.5l-.6 1.6" />
    </>
  ),
  mongodb: (
    // Feuille : silhouette de la marque.
    <>
      <path d="M12 3c3 3.5 4.5 6.5 4.5 9.5S14.5 18.5 12 20c-2.5-1.5-4.5-4.5-4.5-7.5S9 6.5 12 3z" />
      <path d="M12 6.5v13" />
    </>
  ),
  elasticsearch: (
    // Barres empilées de longueurs décroissantes (index inversé).
    <>
      <path d="M5 6h14M4 10h13M6 14h12M8 18h9" />
    </>
  ),
  warehouse: (
    // Entrepôt de données : cylindre large + strates.
    <>
      <ellipse cx="12" cy="6.5" rx="8" ry="2.8" />
      <path d="M4 6.5v11c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-11" />
      <path d="M4 11.5c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8" />
      <path d="M4 16c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8" />
    </>
  ),
  bucket: (
    // Stockage objet : seau tronconique.
    <>
      <path d="M4 6h16l-1.8 13.2a1 1 0 0 1-1 .8H6.8a1 1 0 0 1-1-.8z" />
      <path d="M5.2 11h13.6" />
    </>
  ),
  storage: (
    <>
      <rect x="3" y="5" width="18" height="6" rx="1.5" />
      <rect x="3" y="13" width="18" height="6" rx="1.5" />
      <path d="M7 8h.01M7 16h.01" />
      <path d="M11 8h6M11 16h6" />
    </>
  ),
  cache: (
    // Mémoire rapide : éclair dans une puce.
    <>
      <rect x="4" y="6" width="16" height="12" rx="1.5" />
      <path d="M13 9l-3 3.5h2.4L11.5 15l3-3.5h-2.4z" />
    </>
  ),
  backup: (
    <>
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20 4v4h-4" />
      <path d="M12 8.5v4l2.5 1.5" />
    </>
  ),
  datalake: (
    // Nappe de données : strates ondulées.
    <>
      <path d="M3 8c3-1.6 6-1.6 9 0s6 1.6 9 0" />
      <path d="M3 13c3-1.6 6-1.6 9 0s6 1.6 9 0" />
      <path d="M3 18c3-1.6 6-1.6 9 0s6 1.6 9 0" />
    </>
  ),
  file: (
    <>
      <path d="M6 3h7l5 5v13H6z" />
      <path d="M13 3v5h5" />
    </>
  ),
  folder: <path d="M3 7a1 1 0 0 1 1-1h5l2 2.5h8a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />,

  // ── Réseau ──────────────────────────────────────────────────────────────
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
    </>
  ),
  router: (
    <>
      <rect x="3" y="13" width="18" height="7" rx="1.5" />
      <circle cx="7" cy="16.5" r="0.9" fill="currentColor" stroke="none" />
      <path d="M12 13V8M12 8l-3-3M12 8l3-3" />
    </>
  ),
  switch: (
    <>
      <rect x="3" y="9" width="18" height="8" rx="1.5" />
      <path d="M7 9V6M11 9V6M15 9V6M19 9V6" />
    </>
  ),
  firewall: (
    // Mur de briques + flamme.
    <>
      <rect x="3" y="9" width="18" height="11" rx="1" />
      <path d="M3 14.5h18M9 9v5.5M15 14.5V20M9 14.5V20M15 9v5.5" />
      <path d="M12 7c1.6-1.2 1-3 1-3s2.5 1.4 2.5 3.6" />
    </>
  ),
  'load-balancer': (
    // Répartition : une entrée, trois sorties.
    <>
      <path d="M3 12h5" />
      <circle cx="10" cy="12" r="2" />
      <path d="M12 12h3M15 12l3-5M15 12h4M15 12l3 5" />
      <circle cx="19.5" cy="7" r="1.4" />
      <circle cx="19.5" cy="17" r="1.4" />
    </>
  ),
  gateway: (
    // Portail : arche + flux traversant.
    <>
      <path d="M5 20V9a7 7 0 0 1 14 0v11" />
      <path d="M9 20v-7a3 3 0 0 1 6 0v7" />
      <path d="M2 20h20" />
    </>
  ),
  cdn: (
    // Diffusion depuis un centre vers des points de présence.
    <>
      <circle cx="12" cy="12" r="2.5" />
      <circle cx="4.5" cy="6.5" r="1.5" />
      <circle cx="19.5" cy="6.5" r="1.5" />
      <circle cx="4.5" cy="17.5" r="1.5" />
      <circle cx="19.5" cy="17.5" r="1.5" />
      <path d="M10.2 10.4L6 7.6M13.8 10.4L18 7.6M10.2 13.6L6 16.4M13.8 13.6L18 16.4" />
    </>
  ),
  dns: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3.5 9.5h17M3.5 14.5h17" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
    </>
  ),
  vpn: (
    // Tunnel chiffré : conduit + cadenas.
    <>
      <path d="M3 8h11a5 5 0 0 1 0 8H3" />
      <rect x="14" y="10.5" width="6" height="5" rx="1" />
      <path d="M15.8 10.5V9.2a1.7 1.7 0 0 1 3.4 0v1.3" />
    </>
  ),

  // ── Sécurité ────────────────────────────────────────────────────────────
  lock: (
    <>
      <rect x="5" y="10.5" width="14" height="10" rx="1.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="12" r="4" />
      <path d="M12 12h9M18 12v3.5M15.5 12v2.5" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7.5 3v6c0 4.2-3 7.4-7.5 9-4.5-1.6-7.5-4.8-7.5-9V6z" />
    </>
  ),
  certificate: (
    <>
      <rect x="4" y="4" width="16" height="12" rx="1.5" />
      <path d="M8 8h8M8 11h5" />
      <circle cx="16" cy="17.5" r="2.5" />
      <path d="M14.6 19.6L14 22.5l2-1 2 1-.6-2.9" />
    </>
  ),
  vault: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 8V6M12 18v-2M8 12H6M18 12h-2" />
    </>
  ),

  // ── Messages & événements ───────────────────────────────────────────────
  queue: (
    <>
      <rect x="3" y="9" width="4" height="6" rx="1" />
      <rect x="9" y="9" width="4" height="6" rx="1" />
      <rect x="15" y="9" width="4" height="6" rx="1" />
      <path d="M20 12h2M21 10l1 2-1 2" />
    </>
  ),
  kafka: (
    // Nœuds de topic reliés à un axe central (silhouette du logo).
    <>
      <circle cx="12" cy="4.5" r="1.8" />
      <circle cx="12" cy="19.5" r="1.8" />
      <circle cx="18" cy="9" r="1.8" />
      <circle cx="18" cy="15" r="1.8" />
      <path d="M12 6.3v11.4M12.9 10.2l3.5-.9M12.9 13.8l3.5.9" />
    </>
  ),
  event: (
    // Impulsion émise.
    <>
      <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
      <path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 16.5a6.4 6.4 0 0 0 0-9" />
    </>
  ),
  webhook: (
    <>
      <circle cx="8" cy="7.5" r="3" />
      <path d="M9.6 10.1L6 17h5" />
      <circle cx="17" cy="14" r="3" />
      <path d="M14.4 12.6L11 6.5" />
      <path d="M14 17h-3" />
    </>
  ),
  email: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="1.5" />
      <path d="M3.6 6.6L12 13l8.4-6.4" />
    </>
  ),

  // ── Observabilité ───────────────────────────────────────────────────────
  monitoring: (
    <>
      <rect x="3" y="4" width="18" height="14" rx="1.5" />
      <path d="M6 13l3-3.5 2.5 2.5L15 7l3 4" />
      <path d="M9 21h6" />
    </>
  ),
  metrics: (
    <>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </>
  ),
  log: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  trace: (
    // Trace distribuée : segments en cascade.
    <>
      <path d="M3 6h12M3 12h8M3 18h15" />
      <circle cx="17" cy="6" r="1.4" />
      <circle cx="13" cy="12" r="1.4" />
      <circle cx="20" cy="18" r="1.4" />
    </>
  ),

  // ── Développement & livraison ───────────────────────────────────────────
  github: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 6.5l1.5 2M16 6.5l-1.5 2" />
      <circle cx="9.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <path d="M9 16c1 1 5 1 6 0" />
    </>
  ),
  git: (
    // Branche : tronc + dérivation.
    <>
      <circle cx="7" cy="6" r="2.2" />
      <circle cx="7" cy="18" r="2.2" />
      <circle cx="17" cy="10" r="2.2" />
      <path d="M7 8.2v7.6M7 13c0-2 1.5-3 4-3h3.8" />
    </>
  ),
  pipeline: (
    // Étapes CI enchaînées.
    <>
      <circle cx="5" cy="12" r="2.2" />
      <circle cx="12" cy="12" r="2.2" />
      <circle cx="19" cy="12" r="2.2" />
      <path d="M7.2 12h2.6M14.2 12h2.6" />
    </>
  ),
  code: <path d="M8.5 8L4 12l4.5 4M15.5 8L20 12l-4.5 4M13.5 5l-3 14" />,
  package: (
    <>
      <path d="M12 3l8 4.2v9.6L12 21l-8-4.2V7.2z" />
      <path d="M4.3 7.4L12 11.4l7.7-4M12 11.4V21" />
    </>
  ),
  api: (
    <>
      <path d="M8 5c-2 0-2 2-2 3.5S5 12 4 12c1 0 2 0 2 3.5S6 19 8 19" />
      <path d="M16 5c2 0 2 2 2 3.5S19 12 20 12c-1 0-2 0-2 3.5S18 19 16 19" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  docker: (
    <>
      <rect x="4" y="11" width="3" height="3" />
      <rect x="8" y="11" width="3" height="3" />
      <rect x="12" y="11" width="3" height="3" />
      <rect x="8" y="7" width="3" height="3" />
      <path d="M3 15c2 1.5 5 1.5 8 1 3-.5 5-2 6-4" />
    </>
  ),
  kubernetes: (
    <>
      <path d="M12 3l7 4v6l-7 4-7-4V7z" />
      <circle cx="12" cy="10.5" r="2" />
      <path d="M12 3v5M19 7l-5 3.5M5 7l5 3.5M8.5 16.5l1.5-4M15.5 16.5l-1.5-4" />
    </>
  ),

  // ── Acteurs & organisation ──────────────────────────────────────────────
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 19a6 6 0 0 1 12 0" />
      <path d="M16 5.4a3.2 3.2 0 0 1 0 5.2M17 14.2a6 6 0 0 1 4 4.8" />
    </>
  ),
  team: (
    <>
      <rect x="3" y="4" width="18" height="6" rx="1.5" />
      <rect x="3" y="14" width="7" height="6" rx="1.5" />
      <rect x="14" y="14" width="7" height="6" rx="1.5" />
      <path d="M12 10v2M6.5 12v2M17.5 12v2M6.5 12h11" />
    </>
  ),
  service: (
    // Rouage : brique de service.
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
    </>
  ),
}

/** Noms d'icônes disponibles dans le catalogue. */
export const ICON_NAMES = Object.keys(ICONS) as IconName[]

export type IconName = keyof typeof ICONS
