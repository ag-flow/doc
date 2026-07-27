# Broadsheet — système de design de docflow

Composition éditoriale : papier, encre, un seul sérif. **Cyan** est la seule
couleur interactive, **magenta** ne dit que l'échec. La hiérarchie vient de
l'échelle typographique et du blanc — pas de boîtes ni de filets pour
structurer une page.

Référence de recette vivante : **`/design-system`** (route directe, hors
navigation) rend tous les variants et leurs états. Si un variant n'y figure
pas, il n'existe pas dans le système.

## Où vit quoi

| Fichier | Contenu |
|---|---|
| `frontend/src/styles/tokens.css` | **Seul** endroit où une couleur, une police, un espacement, un rayon ou une ombre est écrit littéralement. |
| `frontend/src/styles/base.css` | Défauts d'éléments : `body`, `h1`–`h6`, `p`, `a`, focus, sélection, `.hr`. |
| `frontend/src/styles/components.css` | Primitives en CSS plat : `.btn`, `.input`, `.field`, `.card`, `.tag`, `.table`, `.dialog`, `.seg`, `.radio`, `.elev-*`. |
| `frontend/src/components/ui/` | Enrobages React (`Button`, `Input`, `Field`, `Tag`) : ils **assemblent des classes**, ils ne stylent pas. |

Un test de garde (`src/test/designSystem.test.tsx`) échoue si un hex, un
`rgb()` ou un `font-family` littéral apparaît hors de `tokens.css`.

## Tokens

**Rôles** — `--color-paper` `#f3f2f2` (fond), `--color-surface` `#eae9e9`
(aplat surélevé : carte, champ, dialogue), `--color-ink` `#201e1d`,
`--color-accent` `#0088b0` (cyan), `--color-accent-2` `#d6006c` (magenta),
`--color-divider` (encre à 16 %, jamais un gris opaque).

**Rampes** — `neutral`, `accent`, `accent-2` en crans 100→900, générées en
OKLCH sur une échelle de clarté partagée : le cran 600 de deux rôles a la même
valeur visuelle. Survol = cran 600, état pressé = cran 700.

⚠️ Le contraste cyan/papier est de **3:1** : bon pour les icônes, le grand
texte et le chrome, **insuffisant pour du texte courant**. Un paragraphe en
accent prend `--color-accent-700` ou plus foncé.

**Typographie** — Source Serif 4 en fonte variable (`@fontsource-variable`,
servie par notre build : aucun CDN). Titres et texte partagent la famille ;
les titres sont en poids `--font-heading-weight` (600). Corps 15px/1.55 ;
`h1` 42 · `h2` 32 · `h3` 25 · `h4` 20 · `h5` 16 · `h6` 13 en petites capitales
espacées (`h6` est un **surtitre**, pas un titre de rang 6).

**Espacement** — densité 1.25× : la base Tailwind est à **5px**, donc `p-2` =
10px, `gap-3` = 15px, `p-4` = 20px. Les mêmes valeurs sont disponibles en CSS
via `--space-1..8`. Ne pas resserrer : l'aération fait partie du système.

**Rayons** — `--radius-sm` 1px, `--radius-md` 2px (défaut des composants),
`--radius-lg` 4px (dialogue). **Ombres** — `--shadow-sm/md/lg`, teintées encre.

## Utilitaires Tailwind générés

Les tokens `@theme` produisent les utilitaires : `bg-paper`, `bg-surface`,
`bg-accent`, `text-ink`, `text-accent`, `border-accent-2`, `bg-neutral-300`,
`shadow-md`, `rounded-md`… Utiliser ces noms, jamais `bg-[#0088b0]` ni une
classe construite dynamiquement (`bg-accent-${n}` échappe à l'extraction
statique de Tailwind — passer par `style={{ background: 'var(--color-accent-600)' }}`).

## États interactifs — les trois sont obligatoires

1. `:hover` — cran 600 de la rampe (ou encre à 7 % pour un secondaire).
2. État pressé (`:active`) — un cran plus foncé, 700 (ou encre à 14 %).
3. `:focus-visible` — anneau cyan 2px décalé de 2px. Aucun style de focus
   natif ne subsiste (`:focus { outline: none }` est global).

Désactivé : opacité 45 %. Sélection de texte : cyan à 30 %.

## Chrome applicatif

`styles/chrome.css` + `components/AppRail.tsx` · `AppHeader.tsx` · `Breadcrumb.tsx`.

**Rail** — 56px, encre pleine, icônes **Phosphor duotone** (`@phosphor-icons/react`,
`weight="duotone"`) de 20px dans une cible de clic de 40px (`--rail-target`).
Groupe du haut = workspace courant (workspaces, types, blocs, documents,
webhooks, automates), groupe du bas = compte et administration, séparés par un
filet. Aucun libellé permanent : infobulle au survol. L'actif porte la pastille
cyan via `aria-current="page"` — c'est un état du DOM, donc il reste juste sur
navigation directe par URL.

**En-tête** — tête de journal : filet **gras** (2px encre) au-dessus, filet
**fin** (divider) en dessous. À gauche : icône maison (arbre workspaces → blocs),
marque `docflow`, puis le fil d'Ariane. L'en-tête **remplace le titre de page** :
un écran ne réaffiche pas son nom.

**Fil d'Ariane** — `workspace / bloc / document…`, segments cliquables sauf le
dernier (encre pleine). Les écrans hors workspace ont un segment unique (leur
nom, table `STATIC_LABELS`). Un titre long est tronqué **au milieu**
(`lib/truncateMiddle.ts`) et jamais renvoyé à la ligne ; le titre complet reste
en `title`, donc en infobulle.

**Non câblé volontairement** : la recherche globale (fiche dédiée) et les
notifications (aucun backend). Le slot de droite reste vide plutôt que de
porter des boutons morts.

## Tête de section

`components/SectionHead.tsx` — surtitre cyan en petites capitales, filet court
cyan (2px × 44px) prolongé par un filet fin, puis le titre (46px) et ses actions
sur la même ligne de base. C'est le **seul cadre admis en tête d'écran** : pas
de bandeau, pas de carte de titre. Un filtre en tête de section se pose en
simple soulignement (`border-0 border-b`), pas en champ encadré.

## Listing éditorial

Un index se lit comme une page, pas comme une grille de cartes : une ligne par
objet, filet fin entre les lignes, numérotation à deux chiffres à gauche, label
en sérif 22px, slug en cyan discret, description tronquée, compteurs et
dernière activité à droite (`lib/relativeDate.ts`). Survol = encre à 4 % sur
toute la ligne, **aucune bordure**. La ligne entière est un `<button>` — donc
focusable au clavier sans `tabIndex`. Les actions de fin de ligne vivent **hors**
de ce bouton et apparaissent au survol *ou au focus* (`focus-within`), sinon
elles deviennent inatteignables au clavier.

## Conventions

- `.card` est réservée aux **items discrets d'un listing**, jamais à la mise
  en page.
- Le magenta ne coexiste pas avec le cyan dans un même composant : il signale
  l'échec (message d'erreur, bouton destructif, tag de rejet) et rien d'autre.
- Un écran repris de la maquette peut utiliser les classes `.btn`/`.input`/…
  directement ; les composants `ui/` sont là pour les variants et l'a11y.
