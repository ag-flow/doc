# DEP-02 — `scripts/*.sql` : copies périmées et divergentes des migrations

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : déploiement / migrations
- **Fichiers** : `scripts/0001_init.sql` … `scripts/0013_automation_tracking.sql`, `scripts/db` — vs `backend/migrations/`

## Description

10 fichiers SQL dans `scripts/` sont d'anciennes versions des migrations, avec une **numérotation obsolète en collision** (ex. `scripts/0003_document_versioning.sql` vs `migrations/0003_workspace_template_import.sql`). Deux fichiers **divergent du schéma canonique** :

- `scripts/0009_document_reference.sql` : `target_ref uuid NOT NULL`, `target_label text` nullable, FK dure — la canonique `migrations/0015` a `target_ref` **nullable**, `target_label NOT NULL`, **pas** de FK workspace.
- `scripts/0010_document_title_search.sql` : index **sans** `IF NOT EXISTS` (non rejouable) vs `migrations/0016`.

S'y ajoute `scripts/db`, fichier vide de 0 octet (artefact commité).

## Scénario de reproduction

Quelqu'un applique manuellement `scripts/0009` sur une base → schéma incompatible avec le code (`target_ref NOT NULL` casse les liens orphelins), ou copie un fichier `scripts/` dans `migrations/` → collision de numéro et corruption du runner `apply`.

## Impact

Source de vérité ambiguë ; risque de corruption de schéma sur une application manuelle.

## Piste de correction

Supprimer `scripts/*.sql` et `scripts/db` ; `backend/migrations/` est l'unique source de vérité (principe déjà acté dans CLAUDE.md).
