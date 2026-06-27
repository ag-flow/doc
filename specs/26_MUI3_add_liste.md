# MUI-3 — Flux Add & liste de documents (TanStack)

**Objectif.** L'écran central du bloc : la liste/arbre des documents, personnalisable (colonnes = propriétés), filtrable/triable, et le flux **Add** qui respecte la grammaire des types.

**Dépend de.** `23_MTC` (types autorisés, création, arbre), `21_RW` (valeurs pour les colonnes), `22_MDB` (bloc).

## Flux Add (règle unique, côté IHM)

Un bouton **+** contextuel (à la racine du bloc et sur chaque nœud). Au clic, on appelle « types autorisés » (`block_id, parent?`) :
- **0** → bouton désactivé/absent (feuille).
- **1** → création directe : on demande le **titre**, on crée (création deux temps de `23_MTC`), le nœud apparaît.
- **2+** → petit sélecteur de **type** d'abord (le type conditionne les propriétés), puis titre, puis création.

Création **en deux temps** : Add crée le nœud (titre + type + parent) ; l'édition (contenu + propriétés) se fait ensuite en ouvrant le document. Pas de saisie de contenu dans le Add.

## Liste / arbre (TanStack Table)

- **TanStack Table** (MIT, headless), stylé shadcn/ui + Tailwind → rendu « Linear/Notion » qu'on possède (pas de tree-data payant type MUI Pro).
- **Deux modes** (toggle) :
  - **Arbre** : indentation par `parent`, chevrons d'expansion, guides verticaux. Pas de tri global (il casserait la hiérarchie) ; tri **intra-fratrie** seulement.
  - **Liste plate** : tri/filtre libres sur toutes les colonnes.
- **Colonnes = propriétés à remonter**, pilotées par les `properties_defs` du workspace. Dropdown « Colonnes » pour choisir. **Union des propriétés** sur un arbre mixte : une colonne absente d'un type → **cellule vide** (pas d'erreur).
- **Filtre préservant le chemin** : un nœud retenu garde ses ancêtres visibles (algo de `23_MTC`).
- **Statuts** : rendus en **pastille** via la `color` des `allowed_values` — même renderer que le panneau de propriétés (cohérence visuelle).

## Données

- Arbre à plat : `GET arbre du bloc` (titre dénormalisé → pas de jointure).
- Valeurs des colonnes : valeurs courantes par propriété (jointure head→version côté `21_RW`). Pour une liste, batcher la lecture des valeurs des documents visibles.

## Tâches

- [ ] Table TanStack : colonnes dynamiques (depuis `properties_defs`), visibilité de colonnes, tri, filtre.
- [ ] Mode Arbre (expansion sub-rows, indentation, guides) + mode Liste plate (toggle).
- [ ] Filtre préservant le chemin (réintégration des ancêtres).
- [ ] Bouton **+** contextuel → « types autorisés » → 0/1/2+ → création deux temps.
- [ ] Colonnes union + cellules vides ; pastilles statut (renderer partagé).
- [ ] Tests Vitest : 0/1/2+ au Add, filtre garde les ancêtres, colonne absente = vide.

## Definition of Done

1. `npm run build` + Vitest verts.
2. Dans un bloc `epic` peuplé : l'arbre affiche epic ⊃ feature ⊃ {story, atdd} indenté ; toggle Liste plate trie par `statut`.
3. Dropdown Colonnes : ajouter `budget_jours` → colonne pleine sur les epics, **vide** sur les features/stories.
4. **+** sous une `feature` → sélecteur {story, atdd} ; choisir `story`, saisir titre → le nœud apparaît, ouvrable pour édition.
5. Filtre `statut=done` : les ancêtres des nœuds trouvés restent visibles.
6. **Context7** consulté pour TanStack Table avant code.

## Notes

- Tri global réservé au mode **Liste plate** (incompatible avec l'arbre, par construction).
- Vues sauvegardables (colonnes + filtres mémorisés) : extension future, hors scope.
