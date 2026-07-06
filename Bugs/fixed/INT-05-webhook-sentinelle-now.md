# INT-05 — Collision de sentinelle `"now()"` dans l'UPDATE webhook

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : intégrations / webhooks
- **Fichiers** : `backend/src/docflow/webhooks/service.py:149-166` (`update_webhook`)

## Description

La clause SET est construite avec `sets["updated_at"] = "now()"` puis `if v == "now()": parts.append(f"{k} = now()")`. La comparaison porte sur **toutes** les valeurs, pas seulement `updated_at`. Si une valeur utilisateur vaut littéralement la chaîne `"now()"` (typiquement `url` ou `label`), elle est injectée comme fonction SQL `now()` au lieu d'être paramétrée. (Pas d'injection SQL : les clés restent whitelistées.)

## Scénario de reproduction

`PATCH` webhook avec `url = "now()"` → génère `SET url = now()` → `now()` renvoie un `timestamptz` affecté à une colonne texte → erreur Postgres 500 (ou corruption si cast implicite).

## Impact

Comportement erroné / 500 sur une valeur d'entrée particulière.

## Piste de correction

Utiliser une sentinelle non représentable en entrée utilisateur (objet marqueur dédié) ou traiter `updated_at` hors de la boucle, comme le fait déjà `automations/service.py`.
