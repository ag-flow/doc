# MVIEW — Vues sauvegardées & boards paramétrables

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

**Objectif.** Définir, nommer et **sauvegarder des vues** filtrées / triées / groupées sur les documents d'un workspace (ou d'un bloc), affichées en plusieurs **layouts** (table, board kanban). C'est l'équivalent docflow de **Bases** (Obsidian) et des **queries** (Logseq) — mais **côté serveur**, requêtable, et exposable demain au MCP. Le modèle de données est déjà fait pour : `properties_values` est indexé par workspace et par `allowed_value`.

**Dépend de.** M6 (propriétés), `34_MPTS` (types scalaires — tri/filtre propres), `26_MUI3` (liste/arbre TanStack, colonnes dynamiques), `28_MUI4` (contexte workspace/bloc), board head→version esquissé en `27`. Migration **`0023`** (table `saved_view`).

---

## ⚠ Choix structurants à confirmer avant code

Ces trois décisions façonnent le schéma et l'UI ; les défaire ensuite coûte cher. La spec ci-dessous est construite sur **les recos**, mais elles attendent ton arbitrage.

**A — Expressivité du filtre.**
- **A1 (reco)** : filtre **plat**, conjonction de prédicats AND-és (`statut = prêt` ET `type = feature` ET `echeance < 2026-10-01`). Mappe proprement sur des `EXISTS` indexés (`idx_pvalues_ws` + `idx_pvalues_allowed`), couvre ~90 % des besoins.
- A2 : arbre **AND/OR imbriqué** (comme les *filter groups* d'Obsidian Bases). Plus puissant, mais exige un constructeur de requête récursif et une UI d'arbre.
- *Conséquence* : A1 = engine simple et rapide, additif vers A2 plus tard. A2 d'emblée = surcoût engine + UI immédiat. **Reco A1.**

**B — Portée des vues : partagées vs par-utilisateur.**
- **B3 (reco)** : une vue a un `owner_ref` **nullable** — `null` = **partagée** (tout le workspace la voit), sinon **privée** à son auteur. Le propre et le durable : collaboratif *et* perso.
- B1 : vues de workspace uniquement (toutes partagées) — plus simple, mais pas de « ma vue à moi ».
- *Conséquence* : B3 ajoute une colonne `owner_ref` + une nuance RBAC (qui édite une vue partagée). Coût faible, gain net. **Reco B3.**

**C — Jeu de layouts V1.**
- **C-reco** : **table** + **board (kanban)**. Le board groupé par une propriété `restricted_list` (= statut) est le plus à valeur, et `27` l'esquisse déjà.
- *Conséquence* : `cards` (gère une image de couverture) et `list` = additifs propres ultérieurs. **Reco : table + board en V1.**

---

## Modèle — `saved_view` (`0023`)

| colonne | type | rôle |
|---|---|---|
| `id` | uuid PK | clé technique |
| `workspace_technical_key` | uuid FK → `workspace` CASCADE | scope |
| `bloc_ref` | uuid NULL FK → `data_block` | `null` = tout le workspace ; sinon vue scopée à un bloc |
| `owner_ref` | uuid NULL → utilisateur | `null` = partagée ; sinon privée (décision B) |
| `slug` | text NOT NULL | clé fonctionnelle stable (URL) |
| `label` | text NOT NULL | affiché, renommable |
| `layout` | text CHECK IN (`table`,`board`) | rendu (décision C) |
| `filter` | jsonb NOT NULL default `'[]'` | liste de prédicats AND-és (décision A) |
| `sort` | jsonb NOT NULL default `'[]'` | clés de tri ordonnées `[{field, dir}]` |
| `group_by` | text NULL | slug de propriété ; obligatoire si `layout = board` (doit cibler une `restricted_list`) |
| `columns` | jsonb NOT NULL default `'[]'` | slugs des propriétés affichées en colonnes (table) |
| `created_at` / `updated_at` | timestamptz | audit |

**Unicité** : `UNIQUE(workspace_technical_key, owner_ref, slug)`. Attention PG : `owner_ref NULL` rend l'unicité partielle inopérante sur les vues partagées → poser **deux index uniques partiels** (`WHERE owner_ref IS NULL` et `WHERE owner_ref IS NOT NULL`) ou `COALESCE`. À vérifier/écrire explicitement.

### Forme d'un prédicat (`filter`)

```json
{ "field": "statut", "op": "is", "value": "ready_for_dev" }
{ "field": "echeance", "op": "before", "value": "2026-10-01" }
{ "field": "@type", "op": "is", "value": "feature" }
```

- `field` = **slug de propriété**, ou champ intégré préfixé `@` : `@type`, `@bloc`, `@title`.
- Opérateurs par type : `restricted_list` → `is` / `is_not` / `in` ; `text`/`url` → `contains` / `is_empty` / `not_empty` ; `int`/`float` → `=` `!=` `<` `<=` `>` `>=` ; `date` → `before` / `after` / `on` / `between` ; `bool` → `is_true` / `is_false`.
- `value` référence un **slug** d'`allowed_value` pour `restricted_list` (stable), pas un label.

## Engine de résolution (le cœur)

Traduction du `filter` en **WHERE paramétré** sur les documents du scope. Chaque prédicat de propriété devient un `EXISTS` indexé :

```sql
SELECT d.doc_technical_key, d.title, d.functional_type_ref
FROM   document d
WHERE  d.workspace_technical_key = $1
  AND  ($2::uuid IS NULL OR d.<bloc> = $2)          -- scope bloc optionnel
  AND  EXISTS (                                      -- prédicat : statut = ready_for_dev
        SELECT 1 FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_allowed_values av ON av.id = pv.allowed_value_ref
        WHERE pv.document_ref = d.doc_technical_key
          AND pd.slug = $3 AND av.slug = $4)
  AND  EXISTS ( … )                                  -- AND des autres prédicats
ORDER BY …                                           -- depuis `sort`
```

- **AND-only** ⇒ N `EXISTS` indépendants, tous indexés. (C'est ce qui rend A1 propre ; A2 imposerait un builder récursif.)
- `@type` → jointure `functional_type` sur slug ; `@title` → `ILIKE` ; `@bloc` → lien `document ↔ data_block` (`22`).
- **Jamais d'interpolation** : tout en `$n` (règle `CLAUDE.md`).
- Tri : `sort` traduit en `ORDER BY` ; pour trier sur une propriété, jointure latérale sur `properties_values` (un `LEFT JOIN LATERAL … LIMIT 1` par clé de tri). Pagination par curseur.

### Board (kanban)

`layout = board` + `group_by = <slug restricted_list>` → colonnes = les `properties_allowed_values` de cette propriété, **ordonnées par `position`** ; chaque carte = un document du résultat. **Glisser une carte** d'une colonne à l'autre = écrire la valeur de statut via le PATCH de propriété existant (`21_RW`), donc **lock optimiste 409** réutilisé tel quel (aucun merge serveur).

## Endpoints

```
POST   /ws/{wsSlug}/views                      → créer (filtre owner = appelant ou partagée)
GET    /ws/{wsSlug}/views                      → lister (partagées + privées de l'appelant)
PATCH  /ws/{wsSlug}/views/{slug}               → éditer
DELETE /ws/{wsSlug}/views/{slug}               → supprimer
GET    /ws/{wsSlug}/views/{slug}/results?cursor= → résoudre la vue (documents + colonnes, trié/groupé, paginé)
```

RBAC : lecture du workspace pour **utiliser** une vue ; un utilisateur édite/supprime **ses** vues ; une vue **partagée** est éditable par son auteur (et un admin workspace) — *réglage fin en décision ouverte*.

## Tâches (TDD)

- [ ] Migration `0023` (`saved_view`, index uniques partiels owner null/non-null) + `apply` idempotent.
- [ ] Builder de WHERE paramétré depuis `filter` (AND d'`EXISTS`), testable isolé : un prédicat par type d'opérateur, échappement `$n`.
- [ ] Champs intégrés `@type` / `@bloc` / `@title`.
- [ ] Tri multi-clés (propriété + champ intégré) ; pagination curseur.
- [ ] Board : colonnes = allowed_values ordonnées `position` ; déplacement de carte → PATCH statut + 409 sur version périmée.
- [ ] CRUD `saved_view` scopé (partagées + privées de l'appelant) + RBAC.
- [ ] Front : éditeur de vue (filtre plat, choix layout/colonnes/tri/group), rendu table + board (TanStack Query, dnd board).
- [ ] Context7 avant code (TanStack Query, lib drag-and-drop retenue, génération SQL paramétrée asyncpg).

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build`.
2. Migration `0023` rejouable base vierge **et** existante ; `apply` idempotent ; unicité owner null/non-null correcte (test de doublon).
3. Aucune requête non paramétrée (le builder de filtre est l'endroit le plus à risque — test anti-injection ciblé). Context7 consulté.

### Critères fonctionnels
4. Créer une vue avec ≥ 2 prédicats AND → les `results` ne renvoient **que** les documents satisfaisant **tous** les prédicats.
5. Tri appliqué (asc/desc, sur propriété scalaire et sur champ intégré) ; pagination cohérente.
6. Board : colonnes = statuts ordonnés par `position` ; chaque document tombe dans la bonne colonne.
7. Déplacer une carte écrit le statut ; un déplacement sur version périmée renvoie **409 + état courant** (pas de merge serveur).
8. Vue **privée** invisible aux autres ; vue **partagée** visible de tout le workspace ; isolation cross-workspace prouvée.
9. Renommer une `allowed_value` (label) ne casse aucune vue (le filtre pointe le **slug**).

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes prouve la valeur de bout en bout :

1. Dans `projet-x`, créer une vue **« À développer »** : layout **board**, `group_by = statut`, filtre `@type is feature`, tri `echeance asc`. Enregistrer.
2. Le board affiche les colonnes **Backlog / Prêt / En cours / Fait** (ordre = `position` des statuts) ; les features se rangent dans leur colonne, triées par échéance.
3. **Glisser** une carte de « Prêt » vers « En cours » → le statut du document est écrit ; rouvrir le document confirme le nouveau statut.
4. Créer une 2ᵉ vue **« Échéances proches »** : layout **table**, colonnes `[title, statut, echeance]`, filtre `echeance before 2026-10-01`, tri `echeance asc` → on obtient une liste serrée, exploitable d'un coup d'œil.
5. Marquer **« À développer »** comme **partagée** (owner null) → un collègue du workspace la retrouve ; garder **« Échéances proches »** privée → lui ne la voit pas.
6. Renommer le statut « Prêt » en « Prêt pour dev » → les deux vues **continuent de fonctionner** (filtre sur slug, pas label).

**Ce que ça apporte.** Le modèle de propriétés typées devient une **base requêtable** : on cesse de faire défiler l'arbre pour « trouver les features prêtes dont l'échéance approche » — on **interroge**. C'est le « Bases » de docflow, en self-hosted, et la même surface de requête pourra demain être exposée aux agents via le MCP.

## Notes / décisions ouvertes

- **Édition d'une vue partagée** : seul l'auteur + admin workspace, ou tout membre ? Défaut : **auteur + admin**. À confirmer.
- **A2 (AND/OR imbriqué)** : reporté ; rouvrir si un besoin réel de disjonction émerge.
- **`cards` / `list`** : layouts additifs ultérieurs (cards = gestion d'image de couverture).
- **Vue par défaut d'un bloc** : faut-il qu'un bloc ait une vue « épinglée » ouverte par défaut ? Hors V1, à cadrer avec `28_MUI4`.
- **Exposition MCP des vues** : une vue résolue est un candidat naturel d'outil MCP en lecture (`M10`). Pensé ici, implémenté au milestone MCP — ne pas retordre le DTO de `results` à ce moment-là.
