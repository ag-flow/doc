# MUI-2 — Panneau de propriétés

**Objectif.** Le panneau d'édition des valeurs de propriété d'un document : affichage **dynamique** selon le type, validation, et résolution de conflit **par champ**.

**Dépend de.** `21_RW` (read/write valeurs versionnées + 409/422), `24_MUI1` (à côté de l'éditeur).

## Rendu dynamique (component map maison)

- Les champs affichés viennent des `properties_defs` du `functional_type` du document (pas de schéma en dur).
- **Component map** (≈ 3 types) : `text → input`, `int → number`, `restricted_list → select` (options = `properties_allowed_values`, pastille de `color`, ordre par `position`).
- Choix acté : **pas** de lib form-from-schema (RJSF/Uniforms). Modèle petit et fermé → map maison, qui épouse le versioning **par propriété** (un champ = un éditeur = un save indépendant).

## Machine à états — PAR CHAMP

Chaque champ est autonome ; pas de submit global.

```
idle ──édition──> dirty ──save──> saving
                                    ├─200─> idle      (version bumpée, baseVersion màj)
                                    ├─409─> conflict   (3 valeurs affichées)
                                    └─422─> error      (message de contrainte)
```

État local d'un champ : `status`, `value`, `baseVersion` (= `expected_version`), `conflict?`.

- **save** : `PUT …/values/{def} {value|allowed_value, expected_version: baseVersion}`.
- **200** : `baseVersion = nouvelle version`, retour `idle`.
- **422** : affiche le `message` de la contrainte ; champ reste éditable (validation, pas conflit).
- **409** : le corps fournit `{server_value, server_version}` ; avec l'ancêtre côté client → encart 3 valeurs. **Aucun second appel.**

## Encart conflit (par champ)

Affiche **base / serveur / toi** via le **même renderer** que l'affichage (statut en pastille, int en chiffre, text en clair). Trois sorties, qui **recalent toutes `baseVersion` sur la version serveur** :

- **Garder serveur** → `value = server`, `baseVersion = serverVersion`, `idle`. Aucune écriture.
- **Garder ma valeur** → `baseVersion = serverVersion`, puis re-save (re-409 possible → on reboucle).
- **Choisir une autre** → `baseVersion = serverVersion`, rouvre l'éditeur normal du champ (`dirty`).

## Tâches

- [ ] Component map (3 types) + renderer d'affichage réutilisable (lecture/conflit).
- [ ] Hook de champ : machine à états `idle/dirty/saving/conflict/error`, `baseVersion`.
- [ ] Validation locale (contraintes) avant save ; mapping 422→message.
- [ ] Encart conflit 3 valeurs + 3 actions, recalage `baseVersion`.
- [ ] Repli sur `default_value` à l'affichage si valeur absente.
- [ ] Tests Vitest : 200/409/422 par champ, recalage version, indépendance des champs.

## Definition of Done

1. `npm run build` + Vitest verts.
2. Un `statut` (restricted_list) s'affiche en select avec pastilles couleur ; un `budget_jours` en number ; un `ref_jira` en input.
3. `budget_jours = -1` → **422** avec le message de `min`, champ reste éditable.
4. Save d'un `statut` avec version périmée → **409**, encart 3 valeurs, « Garder ma valeur » resave sur la version serveur et réussit.
5. Deux champs édités : un conflit sur l'un **n'affecte pas** l'autre (indépendance par propriété).

## Notes

- Cohérence d'affichage du panneau (un champ recalé peut dater) : un « rafraîchir le panneau » est **hors scope** tant que le besoin n'est pas mesuré.
- Le panneau ne connaît pas l'état conflit de ses enfants : découplage total = ce qui rend « par champ » propre.
