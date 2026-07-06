# MTPL — Templates de contenu par type fonctionnel

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

**Objectif.** Donner à chaque `functional_type` un **squelette de contenu markdown** appliqué à la création d'un document de ce type : sections, titres, cases à cocher, placeholders. Ne pas confondre avec `20_MT` (import de **structure** : types, propriétés, blocs) — ici on parle du **corps** des documents. Apporte la cohérence éditoriale qu'offrent les *templates* de note de Logseq/Obsidian.

**Dépend de.** M4 (`functional_type`), M5 (`document`, contenu markdown), `26_MUI3` (flux Add / création de document). Migration **`0022`** (porteur du modèle de contenu — forme selon décision ouverte n°1).

> **Forme du modèle : tranchée.** Variante retenue = **« un modèle par type »** (colonne `content_template` sur `functional_type`, migration `0022`). L'évolution vers « N modèles nommés par type » (table `document_template` + sélecteur au Add) reste un **additif propre** possible plus tard, sans réécrire cette spec.

## Principe : pré-remplir, pas verrouiller

Le modèle est un **point de départ**, jamais une contrainte. À la création d'un document typé, si le corps est vide, on l'**initialise** avec le modèle du type. L'utilisateur édite ensuite librement (cohérent avec `21_RW`). Aucune resynchronisation a posteriori : changer le modèle d'un type **n'altère pas** les documents déjà créés (pas de couplage rétroactif — comme un template de note classique).

Séparation nette avec les valeurs de propriétés : le modèle porte **le markdown du corps**. Les valeurs par défaut des propriétés sont déjà gérées par `default_value` des `properties_defs` (M6). On ne duplique pas.

## Variables (substitution à la création)

Jeu initial minimal, résolu **une seule fois** au moment de la création (pas de liaison vivante) :

- `{{title}}` — titre saisi à la création.
- `{{date}}` — date du jour, ISO `YYYY-MM-DD`.

Substitution **littérale et sûre** (le markdown est du texte ; pas d'injection de valeur non échappée dans une structure sensible). Jeu extensible plus tard (mêmes précautions que les variables d'automate, `32_MAUTO`).

## Modèle de données (`0022`, variante « un par type »)

Colonne ajoutée à `functional_type` :

| colonne            | type | rôle |
| ------------------ | ---- | ---- |
| `content_template` | text NULL | squelette markdown ; `NULL` ou vide = pas de pré-remplissage |

Additif pur (`ADD COLUMN ... NULL`, instantané), conforme à la Décision 3. Scope workspace hérité de `functional_type`.

## Application à la création (flux Add, `26_MUI3`)

1. L'utilisateur crée un document de type T (via le flux Add existant).
2. Si `T.content_template` est non vide **et** que le corps fourni est vide → initialiser `document.contenu` = modèle après substitution des variables.
3. L'écriture suit la transaction normale de `21_RW` (versioning, change_log, parsing des références `31`).

Action manuelle complémentaire : commande éditeur **« Insérer le modèle du type »** (re-applique le squelette à la demande, ex. document repassé d'un type à l'autre).

## Édition du modèle (UI)

Sur l'écran des types fonctionnels (`28_MUI4`, route `/ws/:wsSlug/types`), chaque type expose un éditeur de `content_template` (zone markdown). Sauvegarde scopée workspace, RBAC inchangé.

## Tâches (TDD)

- [ ] Migration `0022` (`content_template` sur `functional_type`, ou table `document_template` selon décision n°1) + `apply` idempotent.
- [ ] Moteur de substitution `{{title}}` / `{{date}}` (testable isolé : cas avec/sans variables, titre contenant des caractères markdown).
- [ ] Application à la création : corps vide + modèle présent → pré-rempli ; corps fourni → **modèle ignoré** (pas d'écrasement).
- [ ] Commande « Insérer le modèle du type » côté éditeur.
- [ ] Éditeur de `content_template` sur l'écran des types + `npm run build`.
- [ ] Test d'indépendance : modifier le modèle d'un type → les documents existants **inchangés**.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build` côté front.
2. Migration `0022` rejouable sur base vierge **et** existante ; `apply` idempotent.
3. Context7 consulté avant code (BlockNote : insertion de contenu programmatique ; API éditeur).

### Critères fonctionnels
4. Définir un `content_template` sur un type → créer un document de ce type **avec corps vide** pré-remplit le corps avec le modèle substitué.
5. Créer un document **avec un corps déjà saisi** n'écrase jamais ce corps avec le modèle.
6. `{{title}}` et `{{date}}` sont remplacés correctement à la création (et une seule fois).
7. Modifier le modèle d'un type laisse les documents déjà créés intacts.
8. La commande « Insérer le modèle du type » ré-applique le squelette à la demande.

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes dans un workspace de test prouve la valeur de bout en bout :

1. Dans `projet-x`, ouvrir le type **Feature**, coller dans son modèle de contenu :
   ```
   # {{title}}
   > Créée le {{date}}

   ## Contexte
   ## Objectif
   ## Critères d'acceptation
   - [ ] …
   ```
2. Via le flux Add, créer une feature **« Export PDF »** (corps laissé vide) → le document s'ouvre **déjà structuré** : titre, date du jour, et les trois sections vides prêtes à remplir.
3. Créer une seconde feature en **collant directement** un brouillon dans le corps → le modèle **n'écrase pas** le brouillon.
4. Revenir sur le type Feature, ajouter une section « ## Risques » au modèle → la feature « Export PDF » créée à l'étape 2 reste **inchangée** (pas de resync rétroactive).
5. Sur un vieux document repassé en type Feature, lancer **« Insérer le modèle du type »** → le squelette s'ajoute à la demande.

**Ce que ça apporte.** Chaque type impose sa structure éditoriale sans la verrouiller : on ne repart plus d'une page blanche, les Features/ADR/Bugs sont homogènes dès la création, et la rédaction se concentre sur le fond. C'est le pendant « contenu » de ce que `20_MT` fait pour la structure.

## Décisions actées (recos validées)

1. **Un seul modèle par type** (colonne `content_template`). Passage à N modèles nommés = additif futur (table `document_template`).
2. **Variables V1 = `{{title}}` + `{{date}}` uniquement.** Les `{{prop:slug}}` (injection de valeurs de propriétés) sont reportés après `37_MVIEW` — ça lie le modèle au schéma de propriétés et complexifie la substitution.
3. **Modèle standalone en V1** : édité par type dans l'UI, **non** embarqué dans le package d'import `20_MT`. L'intégration au package sera une décision explicite ultérieure.

Réversible : si un besoin émerge (plusieurs gabarits, variables de propriétés, import packagé), chacun est un additif sans réécriture.
