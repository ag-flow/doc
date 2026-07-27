# MCMP — Composants d'affichage

**Objectif.** Doter l'éditeur d'une boîte à outils de composants d'illustration à fort impact narratif (chronologie, graphique), insérables à la main comme émettables par un agent, rendus nativement dans docflow.

**Dépend de.** `39_MBC` (registre de codecs) — impératif. `24_MUI1` (éditeur).

## Intention

Reprise d'une pratique observée sur un outil tiers : un jeu **restreint** de composants que l'auteur — humain ou agent — insère pour illustrer son propos. L'enjeu n'est pas la parité avec un outil de BI, c'est l'**impact du message** dans un document de travail.

Deux contraintes en découlent :

1. **La source reste en clair dans le markdown.** Composant cherchable en plein texte, diffable en git, relisible par un agent, exportable en tableau si le rendu tombe. Aucune donnée dans un blob opaque, aucune image.
2. **La syntaxe doit être émettable par un LLM sans essai-erreur.** Peu de niveaux, pas d'échappement complexe, une ligne par enregistrement.

## Grammaire commune

### Enveloppe : fence à info string

    ```df-timeline title="Plan d'action immédiat"
    Analyse Data | Récupération des extraits de volumétrie.
    Cadrage Métier | Réunion jeudi pour définir les règles.
    ```

- **Fence CommonMark** : traversée garantie par le parseur, dégradation en bloc de code lisible si le composant est inconnu, aucune balise orpheline en cas de repli.
- **Préfixe `df-`** : réserve l'espace de noms. Sans lui, un bloc de code légitimement étiqueté `chart` deviendrait un graphique. `mermaid` reste sans préfixe — c'est un standard de fait, déjà en place.
- **Attributs** : `clé="valeur"`, valeur toujours entre guillemets doubles, `\"` échappé. `title` est commun à tous les composants.

### Corps : grammaire `records`

Une ligne = un enregistrement, champs séparés par `|`, espaces autour ignorés, `\|` pour un pipe littéral, lignes vides ignorées.

- Ligne d'en-tête **optionnelle**, déclarée explicitement par l'attribut `header="true"`. Pas de détection heuristique : un en-tête deviné se trompera un jour, silencieusement.
- Champs manquants en fin de ligne : tolérés, valeur vide.
- Champs en excès : ignorés, avec diagnostic.

Le parseur de corps est **partagé** (`lib/blockCodecs/records.ts`), pas réécrit par composant.

### Validation et dégradation

Chaque composant déclare un schéma **zod** (déjà dans la stack) pour ses attributs et ses lignes. Règles communes :

- Ligne non conforme → la ligne est rendue en texte brut, le reste du composant s'affiche, un badge « n ligne(s) ignorée(s) » apparaît.
- Attribut inconnu ou valeur hors vocabulaire → rendu par défaut + badge.
- **Jamais** d'échec silencieux ; **jamais** de rendu bloqué pour le reste du document.

C'est le garde-fou principal du lot : ces composants seront majoritairement produits par des agents, donc parfois mal formés.

## Composants du lot

### `df-timeline`

Chronologie ordonnée d'étapes.

- **Corps** : `titre | description`.
- **Attributs** : `title`, `label` (préfixe d'étape, défaut « Étape »).
- **La numérotation est positionnelle**, jamais écrite dans le corps. Un numéro stocké oblige à renuméroter à chaque insertion, et un agent qui régénère la liste se trompera. Un marqueur libre par ligne (« Q1 », « J+3 ») est un besoin de v2, volontairement écarté ici.
- **Rendu** : rail vertical, puce par étape, libellé `LABEL N` en capitales discrètes, carte titre + description.

### `df-chart`

Graphique de répartition ou de série.

- **Corps** : `libellé | valeur[ | valeur…]`. Une valeur = série unique anonyme. N valeurs = N séries, nommées par la ligne d'en-tête si `header="true"`.
- **Attributs** : `type` (vocabulaire contrôlé : `pie` | `donut` | `bar` | `line`), `format` (`count` par défaut | `percent`), `title`, `header`, et **`source` réservé — non implémenté dans ce lot**.
- **Validations spécifiques** :
  - `format="percent"` et somme hors de 100 ± 0,5 → badge « la répartition ne totalise pas 100 % ». Le rendu normalise de toute façon par la somme : **sans ce badge, l'erreur est invisible** et le graphique est plausible mais faux.
  - Valeur non numérique → ligne ignorée + badge.
  - `type` hors vocabulaire → repli en rendu tabulaire + badge.
- **Rendu : SVG maison, sans dépendance.** Les rendus visés font quelques dizaines de lignes de SVG, garantissent la cohérence avec le thème docflow, l'export et l'impression. Une librairie de charting pèse lourd et impose son propre modèle de thème. À rouvrir si le besoin évolue vers des axes composés, du zoom ou des combos — ce sera alors un choix explicite, pas une dérive.

### Hors lot : `flowchart`

**Pas de composant dédié.** `mermaid` est déjà livré (dépendance `mermaid ^11` présente, bloc custom en place) et couvre le graphe orienté avec labels d'arêtes. Un second moteur de graphe serait de la dette pure. Si une syntaxe raccourcie s'avère nécessaire pour les agents, elle sera un **sucre qui compile vers mermaid**, pas un rendu concurrent.

Note de vigilance pour toute syntaxe de graphe future : **l'identité d'un nœud est son libellé exact**. `Public ID` et `Public ID (Clé)` sont deux nœuds. Ne pas corriger cela par une normalisation implicite (casse, parenthèses, espaces) — prévoir une forme `id[Libellé]` et un diagnostic quand deux libellés sont proches.

## Chrome commun

En-tête de composant factorisé, partagé par **tous** les codecs, mermaid et dataset inclus : titre, action « copier la source », action « télécharger » (SVG pour les rendus graphiques, `.md` sinon). Un seul `components/BlockFrame.tsx`, pas une réimplémentation par bloc.

## Insertion

Un item de menu `/` par composant, insérant un squelette **valide et pré-rempli** (deux lignes d'exemple), pas un bloc vide : l'utilisateur découvre la grammaire par l'exemple plutôt que par la documentation.

## Émission par un agent

La grammaire doit être documentée dans `docs/` et atteignable depuis la surface MCP, afin qu'un agent écrivant via `doc__update_document` produise des composants corrects du premier coup. Une grammaire non documentée côté agent sera devinée, donc mal écrite.

## Tâches

- [ ] `lib/blockCodecs/records.ts` : parseur de corps partagé (séparateur, échappement `\|`, en-tête, diagnostics).
- [ ] `components/BlockFrame.tsx` : chrome commun ; y rebrancher `MermaidBlock` et `DatasetBlock`.
- [ ] `lib/blockCodecs/timeline.ts` + `components/TimelineBlock.tsx`.
- [ ] `lib/blockCodecs/chart.ts` + `components/ChartBlock.tsx` (SVG : pie, donut, bar, line).
- [ ] Schémas zod par composant + affichage des diagnostics (badges).
- [ ] i18n `locales/fr.json` : titres du menu slash, messages de diagnostic.
- [ ] Tests Vitest : round-trip par composant, corps malformé, `percent` hors somme, `type` inconnu, échappement `\|`, en-tête multi-séries.
- [ ] Documentation : grammaire dans `docs/`, mise à jour de `FONCTIONNALITES.md` et `guide-utilisateur.md`.

## Definition of Done

1. `npm run build` (tsc strict) + Vitest verts.
2. Insérer une timeline et un chart via `/`, enregistrer, recharger : rendu identique et markdown inchangé au caractère près.
3. Un corps volontairement malformé s'affiche en mode dégradé avec badge, et le reste du document reste rendu.
4. Un `df-chart` en `format="percent"` dont la somme fait 97 affiche le badge de diagnostic.
5. Les deux composants s'affichent à l'identique en mode lecture et en mode édition.
6. **Aucune dépendance npm ajoutée.**
7. Context7 consulté pour BlockNote (`createReactBlockSpec`) avant code.

## Notes

- `source="dataset:<uuid>"` sur `df-chart` : attribut **réservé, non implémenté**. Le mécanisme de référence existe déjà (`dataset://<uuid>`), donc le graphique branché sur un dataset vivant est un lot ultérieur crédible. On réserve l'attribut maintenant pour ne pas avoir à casser la grammaire plus tard.
- Ordre de réalisation : `records.ts` et `BlockFrame.tsx` d'abord (partagés), puis `timeline` et `chart` en parallèle — c'est précisément ce que `39_MBC` rend possible.
