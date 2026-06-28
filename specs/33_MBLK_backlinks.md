# MBLK — Références inverses (backlinks)

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

**Objectif.** Afficher, pour un document, **qui le référence** — la face inverse des liens sortants de `21_RW` / `31_MREF`. Aucune nouvelle écriture : `document_reference` (migration `0015`) est déjà la source de vérité, on l'interroge dans l'autre sens. C'est le « Linked References » que Logseq et Obsidian exposent, ici à coût quasi nul : l'index sur `target_ref` existe déjà.

**Dépend de.** `31_MREF` (table `document_reference`, index `target_ref`), `28_MUI4` (vue document scopée workspace). **Aucune migration** — lecture seule sur l'existant.

## Principe : la table est déjà bidirectionnelle

`document_reference(source_ref → CASCADE, target_ref → molle, target_label, workspace_technical_key)` porte déjà les deux extrémités du lien.

- Liens **sortants** (spec 31) : `WHERE source_ref = :doc`.
- Liens **entrants** (cette spec) : `WHERE target_ref = :doc`.

Le `31` a posé `CREATE INDEX ON document_reference (target_ref)` pour l'anti-join orphelins ; **le même index sert les backlinks**. Rien à migrer, rien à dénormaliser.

Asymétrie héritée de `31` : la `source` est en CASCADE (elle existe toujours quand la référence existe), la `target` est molle. Donc un backlink pointe **toujours vers un document existant** (celui qu'on regarde) depuis une source **garantie présente**. Pas de cas orphelin côté backlinks — l'orphelin, c'est l'inverse (cible disparue), traité en `31`.

## Endpoint

```
GET /ws/{wsSlug}/documents/{id}/backlinks?limit={n}
→ [ { "source_id", "source_title", "source_type", "bloc", "target_label" }, … ]
```

- Jointure `document_reference r JOIN document d ON d.doc_technical_key = r.source_ref`,
  `WHERE r.target_ref = :id AND r.workspace_technical_key = :ws`.
- **Scope workspace obligatoire** (cloisonnement applicatif, comme tout le plan de contenu — `fail closed`).
- `source_title` = titre **courant** de la source (jointure live), pas un libellé figé.
- `target_label` renvoyé pour traçabilité (texte du lien au save) mais l'affichage privilégie `source_title`.
- Requête paramétrée `$1..$n` uniquement.

## UI — panneau « Référencé par »

Dans la vue document (éditeur `24_MUI1` / panneau propriétés `25_MUI2`), un bloc **« Référencé par (N) »** :

- liste les documents entrants : `source_title` cliquable (navigation vers la source), `type` / `bloc` en sous-ligne ;
- liste vide → panneau masqué (ou ligne « Aucune référence entrante ») ;
- chargé via TanStack Query, invalidé quand le document courant ou une source est ré-enregistré.

(option) Compteur de backlinks dans l'en-tête du document, miroir du badge « liens cassés » de la spec 31.

## Tâches (TDD)

- [ ] Endpoint backlinks (jointure source live, scope workspace, limit). Test : A référence B → `backlinks(B)` liste A ; `backlinks(A)` vide.
- [ ] Test d'isolation : une référence créée dans le workspace W2 n'apparaît jamais dans `backlinks` d'un document de W1 (scelle le `fail closed` workspace).
- [ ] Test de fraîcheur : renommer la source A → `backlinks(B)` reflète le nouveau titre (pas le `target_label` figé).
- [ ] Test de retrait : supprimer le lien dans A puis re-save (transaction `21_RW`/`31`) → B ne liste plus A.
- [ ] Panneau « Référencé par » câblé sur l'endpoint + invalidation TanStack Query.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build` côté front.
2. Context7 consulté avant code (TanStack Query : invalidation / `useQuery` async — vérifier l'API installée).
3. Aucune requête SQL non paramétrée ; scope workspace systématique sur l'endpoint (`fail closed`).

### Critères fonctionnels
4. Ouvrir un document → le panneau « Référencé par » liste **tous** les documents du workspace qui le citent, avec leur **titre courant** (jointure live, jamais le `target_label` figé).
5. Le compteur (N) reflète exactement le nombre de sources entrantes ; liste vide → panneau masqué ou « Aucune référence entrante ».
6. Renommer une source → le backlink affiche le nouveau titre sans action manuelle ; retirer le lien dans la source + re-save → le backlink disparaît.
7. Cliquer un backlink → navigation immédiate vers le document source.
8. Une référence émise depuis un autre workspace n'apparaît jamais (isolation prouvée par test).

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes dans un workspace de test prouve la valeur de bout en bout :

1. Dans le workspace `projet-x`, ouvrir la feature **« Spec authentification »**. Le panneau affiche **« Aucune référence entrante »**.
2. Ouvrir un autre document, **« ADR-012 — choix du provider »**. Dans l'éditeur, taper `/link`, chercher `authentification`, choisir « Spec authentification » → un lien s'insère (il affiche le titre, **jamais l'id**). **Sauvegarder.**
3. Revenir sur **« Spec authentification »** → le panneau affiche **« Référencé par (1) »** avec « ADR-012 — choix du provider », cliquable.
4. Cliquer dessus → on arrive directement sur l'ADR. *(On remonte de l'effet à la cause sans fouiller le corpus.)*
5. Renommer l'ADR en **« ADR-012 — adoption de Keycloak »**, revenir sur la spec auth → le backlink affiche le **nouveau** titre.
6. Dans l'ADR, supprimer le lien + **sauvegarder** → revenir sur la spec auth → le backlink a **disparu**.

**Ce que ça apporte.** Avant de modifier un document partagé, on voit d'un coup d'œil **qui en dépend** : l'analyse d'impact (« qui me cite ? ») devient immédiate, là où il fallait auparavant relire ou chercher dans tout le workspace.

## Notes / décisions ouvertes

- **Tri** : par `source_title` (alpha) ou par récence (`created_at` de la référence) ? Défaut proposé : **alpha** (`source_title`). À confirmer.
- **Unlinked references** (mentions du *titre* non encore liées, à la Obsidian) : **hors V1**. Elles imposent un scan du *contenu* par titre → recherche plein-texte, réservée au RAG (frontière posée en `31`). À rouvrir via agflow-rag si le besoin émerge.
- **Backlinks d'un `data_block`** : V1 = documents seulement (les références de `31` sont document→document). Référencer un bloc entier comme cible viendra si/quand le type `reference` (spec `38_MREL`) ouvre des cibles non-document.
- **Pagination** : `limit` simple en V1 ; curseur si un document très cité dépasse l'écran (rare, à mesurer avant d'optimiser).
