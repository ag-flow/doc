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

## Conventions

- `.card` est réservée aux **items discrets d'un listing**, jamais à la mise
  en page.
- Le magenta ne coexiste pas avec le cyan dans un même composant : il signale
  l'échec (message d'erreur, bouton destructif, tag de rejet) et rien d'autre.
- Un écran repris de la maquette peut utiliser les classes `.btn`/`.input`/…
  directement ; les composants `ui/` sont là pour les variants et l'a11y.
