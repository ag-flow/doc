# MT — Import de template

**Objectif.** Cloner la **structure** définie dans un template YAML versionné vers un workspace, de façon idempotente : résolution de l'héritage à l'import, garde-barrière par version, import **purement additif vérifié**, et application **atomique** (tout ou rien ; sur conflit on plante sans rien écrire).

**Dépend de.** M3 (workspace existe), M4 (`functional_type` + statuts), M6 (propriétés `text`/`int` + `constraints`). À placer après ces trois (avant le front). *(Roadmap à mettre à jour si tu valides ce placement.)*

## Principes (rappel des décisions)

- **Template = fichier YAML en git**, pas des tables de template. Le fichier *est* le template. Réf. format : `templates/agile-basic.yaml`.
- On clone la **structure** : `functional_type`, `properties_defs`, `properties_constraints`, `properties_allowed_values`. **Jamais** le contenu (`document`, `data_block`, `properties_values`).
- **Aucun UUID dans le template** : tout par slug. UUID générés à l'import ; les `parent` (self-FK) remappés par slug ; `workspace_technical_key` cible injecté.
- **Héritage = template only, jamais en base.** La base ne connaît que des types concrets à plat. `inherit`, `abstract` n'existent pas en SQL.
- **Les instances vivent dans `document`** (tranché). L'import ne crée pas d'instances.
- **Un type peut avoir plusieurs types d'enfants** (`story` *et* `atdd` ont `parent: feature`). La contrainte « miroir » à la création d'instances (milestone arbre/documents) lira ces `parent` comme l'ensemble des types-enfants autorisés.

## Nouveau bloc modèle

Une seule table, additive — la trace de ce qui a été importé :

```sql
-- migrations/0002_workspace_template_import.sql  (additive)
create table workspace_template_import (
    id                       uuid primary key default gen_random_uuid(),
    workspace_technical_key  uuid not null references workspace(workspace_technical_key) on delete cascade,
    template                 text not null,          -- slug du template (ex. agile-basic)
    version                  integer not null,
    imported_at              timestamptz not null default now(),
    unique (workspace_technical_key, template)
);
```

Sans cette trace, impossible de savoir quelle version est en place : elle est nécessaire, pas optionnelle.

## Format du template (validation pydantic)

```
Template(version:int, template:str, label:str, functional_types:[TypeDef])
TypeDef(slug, label?, abstract:bool=false, inherit:str?, parent:str?|null, properties:[PropDef]=[])
PropDef(slug, label, type:'text'|'int'|'restricted_list', required:bool=false,
        default:str?, constraints:[{kind,value,message?}]=[], allowed_values:[{slug,label,position,color?}]=[])
```

Champs **non hérités** (identité/placement) : `slug`, `parent`, `abstract`.
Champs **hérités & surchargeables** : `label`, `properties`.

## Moteur d'import (4 étapes, calcul AVANT écriture)

1. **Parse + valide** le YAML (pydantic, `extra="forbid"`).
2. **Résout l'héritage** en mémoire :
   - héritage simple (`inherit` unique), **chaînes acycliques** (contrôle de cycle au template → erreur sinon) ;
   - override d'une propriété = **remplacement complet par slug** (pas de fusion partielle des `allowed_values`) ;
   - **écarte les `abstract: true`** (non matérialisés) ;
   - produit la liste **à plat** des types concrets + leurs propriétés résolues.
3. **Diffe** contre l'existant du workspace, par slug → classe chaque élément en *ajout* / *no-op* / *conflit* (table ci-dessous). **Toujours hors transaction, aucune écriture.**
4. **Décide & applique** (voir Atomicité).

## Garde-barrière par version

On lit `workspace_template_import` pour (workspace, template) :

| Comparaison | Action |
| --- | --- |
| version fichier **==** version posée | **no-op total** — on ne diffe même pas, rien à faire |
| version fichier **>** version posée | on applique **si le diff est purement additif** ; sinon **plante** |
| version fichier **<** version posée | **plante** (pas de régression) |

La version est un **contrat** : monter de version *promet* un diff rétro-compatible (additif). L'import *vérifie* la promesse. Un changement cassant ne monte pas la version — il devient **un nouveau template** (autre fichier).

## Sémantique du diff (rétro-compatible vs conflit)

| Changement | Verdict |
| --- | --- |
| type / propriété / allowed_value / type-enfant **absent** côté workspace | **ajout** ✅ |
| identique | no-op |
| `label` modifié | **maj douce** ✅ (cosmétique, ne casse aucune instance) |
| `type` d'une propriété changé | **conflit** 🚫 |
| `required` / `default` / une `constraint` / une `allowed_value` existante modifiée | **conflit** 🚫 |
| `parent` d'un type changé | **conflit** 🚫 |
| élément retiré du template | **ignoré** (jamais de suppression) |

`label` est la **seule** exception modifiable (sinon on ne pourrait jamais corriger une coquille sans casser le ré-import). Tout le reste structurel est bloquant.

## Atomicité (fail-fast, zéro écriture sur conflit)

L'import a **exactement deux issues** : appliqué entièrement, ou rien fait + plantage explicite.

- Analyse (étapes 1→3) **en mémoire, hors transaction**. Aucune écriture pendant le calcul.
- **Un seul conflit dans le lot ⇒ on lève et on sort. Rien n'est écrit.** Pas d'application partielle des ajouts « valides » avant de buter.
- Sinon, **tout dans une seule transaction** : tous les ajouts + bump `version` dans `workspace_template_import`. Un échec technique en cours (contrainte, réseau) ⇒ **rollback total**. Jamais d'ajouts orphelins.

## CLI

```bash
python -m docflow.templates.import --workspace <slug> --file templates/agile-basic.yaml --dry-run
python -m docflow.templates.import --workspace <slug> --file templates/agile-basic.yaml
```

`--dry-run` : affiche *ajouts* + *conflits* + verdict de version, **sans écrire ni planter**. L'import réel, lui, plante sec si la liste de conflits n'est pas vide ou si la version l'interdit.

## Tâches (TDD)

- [ ] Modèles pydantic du template + validation (`extra="forbid"`, types autorisés).
- [ ] Résolution d'héritage : override par slug (remplacement complet), exclusion des `abstract`, **détection de cycle** (`inherit`) → erreur.
- [ ] Remap parent par slug + génération UUID + injection workspace.
- [ ] Diff par slug → classification ajout/no-op/conflit (couvrir chaque ligne de la table).
- [ ] Garde-barrière version : `==` no-op ; `<` plante ; `>` + additif applique ; `>` + altération plante.
- [ ] **Atomicité** : un conflit ⇒ **aucune écriture** (vérifier l'état base inchangé) ; succès ⇒ tout appliqué + version bumpée ; erreur technique en cours ⇒ rollback total.
- [ ] `--dry-run` : ne plante pas, ne écrit pas, liste correcte.
- [ ] migration `0002_workspace_template_import.sql`.

## Definition of Done

1. ruff + mypy + tests verts.
2. Import à blanc d'`agile-basic.yaml` dans un workspace vierge → 5 types concrets matérialisés (base_statusable **exclue**), `epic`/`feature` avec leur `statut` surchargé, `story`/`atdd` avec le `statut` hérité, `atdd` et `story` tous deux enfants de `feature`.
3. Ré-import même version → no-op (rien en base ne bouge, `imported_at` inchangé).
4. Ré-import version supérieure additive (nouvelle propriété) → ajout appliqué + version bumpée.
5. Ré-import version supérieure altérante (un `type` changé) → **plante, base strictement inchangée** (test d'état).
6. Ré-import version inférieure → plante.
7. Pitfalls cochés : requêtes paramétrées, transaction unique, aucun secret, slug = clé.

## Notes / décisions ouvertes

- Numéro de migration `0002` à ajuster si l'archivage workspace (`archived_at`) atterrit d'abord.
- `label` comme seule exception modifiable : posé tel quel ; à confirmer.
- La contrainte « miroir » multi-enfants (un type-instance n'accepte que des enfants dont le type a ce type pour `parent`) est de la responsabilité du milestone **arbre/documents**, pas de l'import — l'import se contente de créer les `functional_type.parent` qu'elle lira.
- **Context7** avant le code (pyyaml, pydantic v2, asyncpg transactions).
