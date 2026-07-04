# DOC-13 — `_fire` webhooks : `asyncio.create_task` sans référence conservée

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : moyenne
- **Zone** : domaine / documents (déclenchement webhooks)
- **Fichiers** : `backend/src/docflow/documents/router.py:31-41`

## Description

L'event loop ne garde qu'une référence **faible** sur les tasks : une task webhook créée par `asyncio.create_task` sans être stockée peut être ramassée par le GC avant exécution → événements `document.created/updated/deleted` perdus sporadiquement.

## Scénario de reproduction

Sous charge/GC agressif, une partie des événements webhook n'est jamais émise (non déterministe).

## Impact

Perte sporadique d'événements webhook.

## Piste de correction

Conserver un set module-level de tasks avec `add_done_callback(set.discard)`.
