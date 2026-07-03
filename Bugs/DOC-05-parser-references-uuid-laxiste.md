# DOC-05 — Parser de références : regex UUID laxiste → 500 + doublons de casse

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute (reproduit par exécution)
- **Zone** : domaine / références
- **Fichiers** : `backend/src/docflow/references/parser.py:7` ; `references/service.py:63`

## Description

Le motif `[0-9a-fA-F-]{36}` matche des chaînes non-UUID (36 hex sans tirets, tirets mal placés, voire 36 tirets). `refresh_references` fait ensuite `uuid.UUID(tid)` **sans try/except** → `ValueError` non attrapée → 500 et rollback de la sauvegarde du document.

Second défaut : le même UUID écrit en MAJUSCULES et en minuscules donne deux clés dans le dict, normalisées vers le même UUID → deux INSERT identiques → `UniqueViolation (source_ref, target_ref)` → 500.

## Scénario de reproduction

- `docflow://doc/aaaaaaaa…(36 hex sans tirets)` → `ValueError: badly formed hexadecimal UUID string` → **impossible de sauvegarder le document**.
- Coller deux fois le même lien en changeant la casse → `UniqueViolationError` → 500.

## Impact

Un lien `docflow://doc/…` légèrement malformé ou dupliqué (casse) rend le document **insauvegardable**, sans message exploitable.

## Piste de correction

Dans `extract_references`, valider par `uuid.UUID(...)` (try/except, ignorer les invalides) et **normaliser la clé** en UUID canonique (déduplication).
