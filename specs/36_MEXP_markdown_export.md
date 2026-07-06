# MEXP — Export markdown + frontmatter

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

**Objectif.** Exporter un workspace en **arbre de fichiers markdown** avec les propriétés en **frontmatter YAML**, dans une archive téléchargeable. Triple gain : **backup lisible** (au-delà du `pg_dump` de `scripts/backup.sh`), **portabilité / non-lock-in**, et **interop directe** — l'export s'ouvre tel quel comme **vault Obsidian** ou s'importe comme **graphe Logseq**. C'est la brique qui rend tangible le positionnement « docflow stocke, agflow-rag indexe — ensemble, l'alternative self-hosted à ce qu'Obsidian fait payer ».

**Dépend de.** M5 (`document`, arbre `parent`, contenu), M6 (`properties_values`, `properties_defs`, `properties_allowed_values`), `22_MDB` (lien `document ↔ data_block`), `28_MUI4` (contexte workspace). **Aucune migration** — lecture seule.

## Principe : projeter le store en fichiers, sans le modifier

L'export est une **projection en lecture seule** de l'état courant. Il ne touche ni le schéma ni les données. La hiérarchie d'information de l'app (`workspace → bloc → arbre de documents`) devient une hiérarchie de dossiers ; les propriétés deviennent du frontmatter ; les liens internes deviennent des liens markdown.

V1 = **export seul** (sens unique). Le ré-import (relecture d'un vault modifié) est un chantier distinct, lié au format de `20_MT` — **hors périmètre** ici (voir décisions actées).

## Arborescence produite

```
<workspace-slug>/
  <bloc-slug>/
    <Titre-doc-racine>.md            ← document racine du bloc
    <Titre-doc-racine>/              ← présent seulement s'il a des enfants
      <Titre-enfant>.md
      <Titre-enfant>/ …
```

- **Top-level = blocs** (mirroir de la navigation `28_MUI4`). Les types fonctionnels ne sont **pas** des dossiers : ils vivent en frontmatter (`type`).
- Un document = un fichier `<Titre slugifié>.md`. S'il a des enfants, on crée **en plus** un dossier homonyme contenant les enfants (pattern « note + sous-dossier », compatible Obsidian).
- **Collisions de noms** entre frères (titres slugifiés identiques) : suffixe court dérivé du `doc_technical_key` (`-a1b2`). Déterministe, pas d'écrasement silencieux.

## Frontmatter YAML (par document)

```yaml
---
docflow_id: 4f3c…           # doc_technical_key — identité stable pour un futur round-trip
title: "Spec authentification"
type: feature               # slug du functional_type (null si document pur)
echeance: 2026-09-15        # propriété date  → valeur sérialisée
publie: false               # propriété bool
charge-jours: 3.5           # propriété float
statut: "Prêt pour dev"     # propriété restricted_list → label (voir décision actée)
---
```

- Clé YAML = **slug** de la propriété (stable, machine-friendly, idéal pour les filtres Obsidian Bases).
- Valeur : scalaires sérialisés selon `34_MPTS` ; `restricted_list` → **label** de l'`allowed_value` (lisible dans l'outil cible — voir décision actée et son revers).
- `docflow_id`, `title`, `type` toujours présents ; les propriétés absentes ne sont pas émises (pas de clés vides).

## Réécriture des liens (interop)

Le contenu porte des liens `docflow://doc/{id}` (`31_MREF`). À l'export :

- cible **dans le périmètre exporté** → réécriture en **wikilink** `[[Titre cible]]` (résolution `id → titre` via la table des documents). Obsidian et Logseq résolvent nativement les `[[ ]]`.
- cible **hors périmètre** ou **orpheline** → on **conserve** le lien d'origine (`[Titre](docflow://doc/{id})`), pas de lien cassé silencieux.

## Endpoint

```
GET /ws/{wsSlug}/export?scope=workspace            → archive zip du workspace
GET /ws/{wsSlug}/export?scope=bloc&bloc={blocSlug} → archive zip d'un seul bloc
```

- RBAC : droit de **lecture** sur le workspace (`fail closed`).
- Réponse : `application/zip` en streaming (ne pas matérialiser tout l'arbre en mémoire pour un gros workspace).
- Requêtes paramétrées ; une seule passe de lecture cohérente (snapshot logique).

## Tâches (TDD)

- [ ] Service de projection : workspace/bloc → arbre `{chemin → contenu}` (testable sans HTTP).
- [ ] Slugification des titres + résolution déterministe des collisions (test : deux frères homonymes → suffixes distincts stables).
- [ ] Sérialisation frontmatter (chaque type de propriété ; `restricted_list` → label ; échappement YAML des valeurs à risque — guillemets, deux-points, multilignes).
- [ ] Réécriture des liens `docflow://` → `[[Titre]]` pour les cibles in-scope ; conservation sinon (test des deux branches).
- [ ] Endpoint zip streamé + RBAC lecture + scope workspace/bloc.
- [ ] Context7 avant code (génération zip en streaming, sérialiseur YAML).

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build` côté front (bouton d'export).
2. Export streamé (pas de chargement complet en mémoire) ; RBAC lecture vérifié.
3. Context7 consulté ; aucune requête SQL non paramétrée ; aucune écriture en base (lecture seule prouvée).

### Critères fonctionnels
4. L'archive reproduit la hiérarchie `bloc → arbre de documents` ; chaque document est un `.md` au bon chemin.
5. Le frontmatter de chaque document contient `docflow_id`, `title`, `type` et toutes ses propriétés valuées, correctement sérialisées et échappées.
6. Les liens internes vers des cibles in-scope sont des `[[wikilinks]]` ; les autres restent intacts (aucun lien cassé fabriqué).
7. Les collisions de noms produisent des fichiers distincts (aucun écrasement).
8. L'archive d'un workspace vide ou d'un bloc vide est produite sans erreur (cas limite).

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes prouve la valeur de bout en bout :

1. Dans `projet-x`, depuis l'écran du workspace, cliquer **« Exporter (markdown) »** → téléchargement de `projet-x.zip`.
2. Dézipper : retrouver l'arbre `projet-x/<bloc>/…`, chaque feature en `.md`, les sous-documents dans des sous-dossiers homonymes.
3. Ouvrir le dossier **comme vault dans Obsidian** : les notes s'affichent, le **frontmatter** est reconnu comme Properties, et les `[[liens]]` internes sont **cliquables** (graphe reconstruit).
4. Activer le core plugin **Bases** dans Obsidian, créer une base filtrée `type is feature`, colonnes `statut`, `echeance` → on **retrouve les propriétés docflow** comme une base de données Obsidian, sans aucune ressaisie.
5. (option) Importer le même `.sqlite`/markdown dans **Logseq** → les pages et références sont reconstruites.

**Ce que ça apporte.** Les données ne sont jamais prisonnières : un workspace docflow devient en un clic un vault Obsidian exploitable (Bases compris) ou un graphe Logseq. Le non-lock-in cesse d'être une promesse pour devenir une commande — et ce qu'Obsidian/Logseq font côté lecture, docflow + agflow-rag le couvrent en self-hosted.

## Décisions actées (recos validées)

- **Valeur des `restricted_list` = label** (lisible dans l'outil cible), clé YAML = slug (stable). *Revers assumé :* un futur ré-import devrait re-mapper les labels (fragile). **Si le round-trip devient un objectif**, basculer la valeur sur le **slug** (ou émettre les deux : `statut: ready_for_dev` + `statut_label: "Prêt pour dev"`) — additif non bloquant.
- **Réécriture des liens in-scope en wikilinks** (interop maximale), conservation des liens hors-scope/orphelins.
- **Périmètre V1 = workspace entier + option bloc.** Sous-arbre arbitraire = additif si besoin.
- **Export seul (sens unique).** Le ré-import est un chantier distinct, couplé au format `20_MT` — explicitement hors V1.

## Notes / décisions ouvertes

- **Pièces jointes / images** : si des images sont intégrées via BlockNote (`24_MUI1`), faut-il les exporter dans un dossier `assets/` et réécrire les chemins ? À cadrer selon la façon dont les images sont stockées aujourd'hui (base ? URL ? data-URI ?) — **à vérifier dans le code réel avant d'écrire** (cf. disclaimer).
- **`data_block` typés** : exporter aussi les blocs structurés (epic/feature data_blocks) ou seulement les documents ? V1 = documents ; les blocs comme métadonnée de chemin. À rouvrir si les blocs portent du contenu propre.
