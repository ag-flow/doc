# INT-01 — Path traversal / écriture arbitraire via `template_slug` (galerie)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : intégrations / templates gallery
- **Fichiers** : `backend/src/docflow/templates/gallery.py:81-96` (`pull_template`) ; `templates/router.py:245-266` (`pull_from_gallery`), `69-73` (`GalleryPullIn`)

## Description

`pull_template` écrit sur disque avec `dest = templates_dir / f"{template_slug}.yaml"` puis `dest.write_text(...)`. `template_slug` provient de `GalleryPullIn.template_slug`, **sans aucune validation** (pas de regex slug, contrairement à `remote/schemas.py`). Rien ne vérifie non plus que le YAML téléchargé porte bien ce slug (`tpl.template == template_slug` non contrôlé).

## Scénario de reproduction

1. `POST /api/templates/gallery/pull` avec `template_slug = "../../../opt/docflow/backend/src/docflow/evil"` et une `source_url` servant un YAML valide.
2. Écriture de `/opt/docflow/backend/src/docflow/evil.yaml` **hors** du répertoire `templates/`.

## Impact

Écriture de fichiers `.yaml` à des chemins arbitraires (écrasement d'autres templates, dépôt de fichiers hors périmètre). Gardé par `require_admin` — donc voir [AUTH-07](../AUTH-07-require-admin-ne-verifie-pas-is-admin.md) pour l'exposition réelle.

## Piste de correction

Valider `template_slug` par la même regex slug que `remote/schemas.py` (`^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$`) avant tout usage, refuser tout slug contenant `/`, `..` ou séparateur, et vérifier que le YAML téléchargé porte le slug attendu.
