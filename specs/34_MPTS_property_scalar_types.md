# MPTS — Types de propriété scalaires (date, bool, url, float)

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

> **Note de schéma (post-`0005`).** Depuis le versioning, `properties_values` est une **tête d'identité** (`document_ref`, `property_def_ref`, `version`) ; la valeur réelle (`value`, `allowed_value_ref`) vit dans **`properties_value_version`**. Cette spec écrit donc dans la table de version, **pas** dans `properties_values`. (En `39_MMV`, ces colonnes descendront encore d'un cran dans `properties_value_item` — voir cette spec.)

**Objectif.** Étendre `properties_defs.type` au-delà de `text` / `int` / `restricted_list` avec **`date`**, **`bool`**, **`url`**, **`float`**. Le stockage ne change pas (la valeur reste un `text` dans `properties_value_version`, sérialisation typée) ; la validation est **applicative** (même moteur que `int`) ; des composants de saisie dédiés côté front. C'est le pré-requis d'un tri/filtre propre, dont dépendent les vues sauvegardées (`37_MVIEW`).

**Dépend de.** M6 (`properties_defs`, `properties_values`, `properties_constraints`, moteur de validation), `25_MUI2` (component map). Migration **`0021`** (élargissement du `CHECK` sur `properties_defs.type`).

## Décisions actées

- **`float` ajouté** dès maintenant (même colonne, même moteur ; éviter une 2ᵉ migration de CHECK plus tard).
- **`date` = jour seul** (forme ISO `YYYY-MM-DD`). Un éventuel `datetime`/fuseau sera un **type distinct**, pas une surcharge.
- **Slugs de type** : `date`, `bool`, `url`, `float` (cohérents avec `text`/`int`, minuscules courts, immuables une fois posés).
- **`url`** : schemes `http` / `https` uniquement en V1.

## Principe : nouveaux types, même mécanisme de valeur

La valeur reste un `text` dans **`properties_value_version`** (`value`). Chaque type définit sa **forme canonique sérialisée** et son **validateur applicatif** (au même endroit que `int` aujourd'hui) :

| type    | forme stockée (`text`)        | validation applicative                       | contraintes applicables |
| ------- | ----------------------------- | -------------------------------------------- | ----------------------- |
| `date`  | ISO-8601 date `YYYY-MM-DD`    | `date.fromisoformat`, rejet sinon            | `min` / `max` (bornes de date) |
| `bool`  | `true` / `false`              | littéral exact (pas de `1`/`oui` laxiste)    | aucune                  |
| `url`   | URL absolue `scheme://…`      | `urlparse` + scheme ∈ {http, https} + netloc | aucune (V1)             |
| `float` | décimal, séparateur `.`       | `float()` strict                             | `min` / `max` (numérique) |

Aucune nouvelle colonne, aucun nouvel `allowed_value`. Ces scalaires utilisent `value` (comme `text`/`int`) ; `allowed_value_ref` reste null pour eux. Le `CHECK(NOT (value IS NOT NULL AND allowed_value_ref IS NOT NULL))` — porté par **`properties_value_version`** depuis `0005` — reste vrai.

## Migration `0021`

Élargir le `CHECK` de `properties_defs.type` (posé inline dans `0001`, ligne ~108, donc auto-nommé `properties_defs_type_check`) :

```sql
-- vérifier le nom réel de la contrainte avant de la dropper (auto-nommée par PG)
ALTER TABLE properties_defs DROP CONSTRAINT properties_defs_type_check;
ALTER TABLE properties_defs ADD CONSTRAINT properties_defs_type_check
    CHECK (type IN ('text','int','restricted_list','date','bool','url','float'));
```

Additif au sens de la Décision 3 : un CHECK **plus permissif** ne rejette aucune ligne existante. Rejouable sur base vierge **et** existante ; `apply` idempotent.

## Validation applicative (extension du moteur M6)

- `date` : `datetime.date.fromisoformat(value)` ; échec → rejet (invariant I-3 étendu au type).
- `bool` : appartenance stricte à `{"true","false"}` ; message clair si autre (`"1"`, `"oui"` refusés).
- `url` : `urllib.parse.urlparse`, `scheme ∈ {http, https}`, `netloc` non vide.
- `float` : `float(value)` strict (rejette `"abc"`, accepte `"-3.14"`).
- `min` / `max` : interprétés **selon le type** — comparaison de dates ISO pour `date`, comparaison numérique pour `int`/`float`.
- `pattern` **reste réservé à `text`** (invariant I-6 inchangé) ; refusé sur date/bool/url/float. → test de rejet. *(Restreindre une `url` à un domaine via `pattern` = additif futur, hors V1.)*
- `default_value` coercé/validé selon le type, comme les autres (M6).

## Frontend (component map, `25_MUI2`)

- `date` → date picker (sortie ISO `YYYY-MM-DD`).
- `bool` → checkbox / switch.
- `url` → input validé + icône d'ouverture en nouvel onglet.
- `float` → input numérique (`step`).

Les états par champ (intact / édité / erreur / conflit) du panneau de propriétés sont inchangés.

## Tâches (TDD)

- [ ] Migration `0021` (CHECK élargi) + `apply` idempotent sur base vierge et existante.
- [ ] Validateurs `date` / `bool` / `url` / `float` testés isolément (cas valides + rejets ciblés).
- [ ] `min`/`max` sur `date` (bornes) et sur `float` (numérique) ; rejet de `pattern` sur tout type ≠ `text`.
- [ ] `required` + `default_value` par nouveau type (coercition + rejet si absent).
- [ ] Component map front (4 composants) + `npm run build`.
- [ ] Context7 avant code (API du date picker shadcn ; rappel `urlparse`/`date.fromisoformat`).

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build` côté front.
2. Migration `0021` rejouable sur base vierge **et** existante ; `apply` idempotent.
3. Context7 consulté avant code ; aucune requête SQL non paramétrée.

### Critères fonctionnels
4. On peut créer une `properties_def` de type `date`, `bool`, `url`, `float` sur un type fonctionnel.
5. Une valeur valide est persistée ; une valeur invalide (date malformée, bool `"oui"`, url sans scheme, float non numérique) est **rejetée avec un message lisible**.
6. `min`/`max` sont respectés sur `date` et `float` ; `pattern` est refusé hors `text`.
7. Le tri d'une liste sur une colonne `date` ou `float` est correctement ordonné (chronologique / numérique, pas lexicographique).
8. Chaque type affiche le bon composant de saisie (picker, switch, input url, input numérique).

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes dans un workspace de test prouve la valeur de bout en bout :

1. Dans `projet-x`, sur le type **Feature**, ajouter quatre propriétés : `échéance` (**date**), `publié` (**bool**), `lien-maquette` (**url**), `charge-jours` (**float**).
2. Créer une feature **« Export PDF »** ; renseigner `échéance = 2026-09-15`, `publié = false`, `lien-maquette = https://figma.com/…`, `charge-jours = 3.5`. **Enregistrer** → tout est accepté.
3. Modifier `échéance` en `15/09/2026` (mauvais format) → **rejet** avec message ; mettre `publié = oui` → **rejet** ; `lien-maquette = figma.com/x` (sans scheme) → **rejet**.
4. Poser une contrainte `min = 2026-01-01` sur `échéance`, tenter `2025-12-31` → **rejet borné**.
5. Créer deux autres features avec des échéances différentes, ouvrir la liste du bloc et **trier par `échéance`** → l'ordre est **chronologique** (et non `"02…" < "15…"` lexicographique).

**Ce que ça apporte.** Les propriétés deviennent de vraies données typées : dates triables, booléens filtrables, liens cliquables, montants comparables. C'est la fondation directe des vues sauvegardées (`37_MVIEW`) — sans types scalaires, un « board trié par échéance » n'a pas de sens.

## Notes / décisions ouvertes

- **`pattern` sur `url`** (restreindre à un domaine) : hors V1, additif si besoin réel.
- **`datetime` / fuseau** : type distinct futur, ne pas surcharger `date`.
- **Localisation de saisie de la date** : le picker affiche au format local mais **stocke ISO** ; vérifier qu'aucune conversion de fuseau ne décale le jour (piège classique — à tester explicitement).
