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
  - `source` : **réservé** (branchement futur sur un dataset), non implémenté.
- Valeur non numérique → ligne ignorée + badge. Virgule décimale acceptée.
- Rendu : SVG natif docflow (aucune dépendance), export SVG via l'en-tête du bloc.

## Graphes orientés : utiliser `mermaid`

Pas de composant `df-flowchart` : les fences ```` ```mermaid ```` sont rendues
nativement et couvrent le graphe orienté. Attention : dans mermaid, **l'identité
d'un nœud est son libellé exact** (`Public ID` ≠ `Public ID (Clé)`) — utiliser
la forme `id[Libellé]` pour un même nœud sous plusieurs libellés.

## Chrome commun

Chaque bloc (timeline, chart, mermaid, dataset) porte un en-tête discret :
titre, **copier la source**, **télécharger** (SVG pour les rendus graphiques,
`.md` sinon).
