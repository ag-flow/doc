# Composants d'affichage — grammaire

> Composants d'illustration insérables dans un document docflow, à la main
> (menu `/`) comme par un agent (via `doc__update_document`). La source reste
> **en clair dans le markdown** : cherchable, diffable, relisible.

## Enveloppe commune : fence à info string

````markdown
```df-timeline title="Plan d'action immédiat"
Analyse Data | Récupération des extraits de volumétrie.
Cadrage Métier | Réunion jeudi pour définir les règles.
```
````

- Fence CommonMark ; un composant inconnu se dégrade en bloc de code lisible.
- Préfixe **`df-`** : espace de noms réservé aux composants docflow
  (`mermaid` reste sans préfixe — standard de fait).
- Attributs : `clé="valeur"`, valeur **toujours entre guillemets doubles**,
  `\"` pour un guillemet littéral. `title` est commun à tous les composants.

## Corps : grammaire `records`

- **Une ligne = un enregistrement**, champs séparés par `|`.
- Espaces autour des champs ignorés ; lignes vides ignorées.
- `\|` pour un pipe littéral.
- Ligne d'en-tête **optionnelle et explicite** : attribut `header="true"`
  (jamais devinée).
- Champs manquants en fin de ligne : tolérés (valeur vide). Champs en excès :
  ignorés, avec diagnostic.

## Validation et dégradation

- Ligne non conforme → rendue en texte brut, le reste s'affiche, badge
  « n ligne(s) ignorée(s) ».
- Attribut inconnu ou valeur hors vocabulaire → rendu par défaut + badge.
- Jamais d'échec silencieux ; jamais de rendu bloqué pour le reste du document.

## `df-timeline` — chronologie d'étapes

````markdown
```df-timeline title="Mise en route" label="Phase"
Cadrage | Définir le périmètre avec le métier.
Prototype | Valider la faisabilité sur un cas réel.
Déploiement | Ouvrir au premier groupe d'utilisateurs.
```
````

- Corps : `titre | description`.
- Attributs : `title`, `label` (préfixe d'étape, défaut « Étape »).
- **La numérotation est positionnelle** — ne jamais écrire de numéro dans le
  corps (l'insertion d'une étape renumérote automatiquement).

## `df-conversation` — échange en bulles

````markdown
```df-conversation title="Point CRM" me="Alice"
Alice | On livre vendredi ?
Bob | Oui, si la recette passe jeudi.
Alice | Je bloque ma journée de jeudi.
```
````

- Attributs : `title`, `me` (ses messages s'alignent à droite),
  `format` (`records` | `transcript` | `vtt` — défaut : détection automatique).
- **Trois formats de corps acceptés** :
  1. `records` (canonique) : `Interlocuteur | message`, une ligne par message ;
  2. `transcript` : en-tête `Interlocuteur • 0:32 \` puis le texte sur les
     lignes suivantes (exports d'outils de transcription) ;
  3. `vtt` : contenu WebVTT (Teams) collé tel quel — voix `<v Nom>…</v>`,
     cues consécutives du même interlocuteur fusionnées, identifiants ignorés.
- L'horodatage (transcript/vtt) s'affiche à côté du nom ; les messages
  consécutifs du même interlocuteur sont groupés sous un seul nom.

## `df-chart` — graphique

````markdown
```df-chart type="donut" title="Avancement" format="percent"
Fait | 60
En cours | 30
À faire | 10
```
````

- Corps : `libellé | valeur[ | valeur…]`. Une valeur = série unique.
  N valeurs = N séries, nommées par l'en-tête si `header="true"` :

````markdown
```df-chart type="bar" title="Charge" header="true"
Mois | Prévu | Réel
Janvier | 10 | 12
Février | 8 | 7
```
````

- Attributs :
  - `type` : `pie` | `donut` | `bar` | `line` (hors vocabulaire → rendu
    tabulaire + badge) ;
  - `format` : `count` (défaut) | `percent` — en `percent`, une somme hors de
    100 ± 0,5 affiche un badge (le rendu normalise par la somme : sans badge,
    l'erreur serait invisible) ;
  - `title`, `header` ;
  - `source="dataset://<uuid>"` : le chart se branche sur un **dataset vivant**
    du workspace courant — le corps records est alors ignoré (il sert de repli
    hors session). Forme `dataset:<uuid>` tolérée ; la forme canonique
    `dataset://<uuid>` est **recommandée** car elle est comptée par le refcount
    de contenu (le dataset référencé n'est pas purgeable). Mapping : 1ʳᵉ colonne
    (par position) = libellés ; colonnes `int`/`float` = séries (nommées par
    leur libellé de colonne). Dataset introuvable → badge + repli sur le corps ;
    aucune colonne numérique → badge + rendu tabulaire.
- Valeur non numérique → ligne ignorée + badge. Virgule décimale acceptée.
- Rendu : SVG natif docflow (aucune dépendance), export SVG via l'en-tête du bloc.

## `df-display` — composition libre (A2UI simplifié)

`````markdown
```df-display title="Comparatif"
[
  {"id": "root", "component": "Column", "children": ["title", "cards"]},
  {"id": "title", "component": "Text", "text": "Comparatif", "hint": "h2"},
  {"id": "cards", "component": "Row", "children": ["c1", "c2"]},
  {"id": "c1", "component": "Card", "children": ["c1t", "c1b"]},
  {"id": "c1t", "component": "Text", "text": "Option A", "hint": "h3"},
  {"id": "c1b", "component": "Badge", "text": "Recommandé", "variant": "accent"},
  {"id": "c2", "component": "Card", "children": ["c2t"]},
  {"id": "c2t", "component": "Text", "text": "Option B", "hint": "h3"}
]
```
`````

- Corps : **tableau JSON plat** (adjacency list) — `id` unique, `component` du
  catalogue, `children` = ids, autres clés = props à plat. Racine = `id "root"`
  sinon le premier composant.
- Fence canonique **`df-display`** ; alias `display` toléré en lecture,
  revendiqué seulement si le corps est un tableau JSON (sinon bloc de code
  ordinaire). La fence d'origine est préservée au round-trip.
- **Catalogue** : Row, Column, Card, List (`ordered`), Divider · Text
  (`hint: h1|h2|h3|body|caption`), Image (`src`, `alt`), Icon (`name`),
  Badge/Chip (`text`, `variant: neutral|accent|alert`) · ProgressBar
  (`value` 0–100, `label`).
- **Image** : `https:` ou artefact docflow (`/api/…`) uniquement — le reste
  rend « image non autorisée ». **Icon** : 30 noms kebab-case stables
  (`check`, `x`, `warning`, `info`, `clock`, `calendar`, `user`, `users`,
  `gear`, `lightning`, `flag`, `star`, `arrow-right`, `arrow-up`,
  `arrow-down`, `link`, `file`, `folder`, `tag`, `chat`, `envelope`, `globe`,
  `lock`, `shield`, `database`, `rocket`, `target`, `trend-up`, `trend-down`,
  `circle`) — inconnu → cercle grisé.
- **Gardes** : 500 composants max, profondeur 32, cycles coupés ; composant
  inconnu → texte grisé (ses enfants rendent) ; doublons/orphelins/références
  mortes → badges de diagnostic, rendu partiel — jamais d'échec.
- Hors MVP (phases ultérieures) : data binding datasets, actions utilisateur,
  Chart/Mermaid/DataTable au catalogue.

## Graphes orientés : utiliser `mermaid`

Pas de composant `df-flowchart` : les fences ```` ```mermaid ```` sont rendues
nativement et couvrent le graphe orienté. Attention : dans mermaid, **l'identité
d'un nœud est son libellé exact** (`Public ID` ≠ `Public ID (Clé)`) — utiliser
la forme `id[Libellé]` pour un même nœud sous plusieurs libellés.

## Chrome commun

Chaque bloc (timeline, chart, mermaid, dataset) porte un en-tête discret :
titre, **copier la source**, **télécharger** (SVG pour les rendus graphiques,
`.md` sinon).
