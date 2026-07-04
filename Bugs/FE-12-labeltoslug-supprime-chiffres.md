# FE-12 — `labelToSlug` supprime les chiffres

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / slug
- **Fichiers** : `frontend/src/lib/slug.ts:2-8`

## Description

La regex `[^a-z-]` remplace aussi les **chiffres** par `-`, alors que les regex de validation (`^[a-z0-9][a-z0-9_-]*$`) les acceptent. « Sprint 2 » → `sprint`, « V2 Docs » → `v-docs`. Incohérent avec les autres `slugify` du code (AddDocumentDialog, RemotePage) qui conservent `0-9`.

## Scénario de reproduction

Saisir un label contenant des chiffres → le slug proposé perd les chiffres.

## Impact

Slugs proposés incohérents et parfois collisionnants.

## Piste de correction

`[^a-z0-9-]`.
