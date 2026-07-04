# AUTH-01 — Callback OIDC émet un JWT sans vérifier la signature de l'id_token

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Fable.
> Flow authorization-code complet côté serveur : `POST /api/auth/oidc/callback` accepte
> désormais `{code, redirect_uri, nonce?}` (plus jamais de claims bruts). Le backend
> échange le `code` au token endpoint (client_secret résolu via vault, auth basic),
> puis vérifie lui-même l'id_token : signature contre le JWKS découvert via
> `.well-known/openid-configuration` (cache 300 s, re-fetch unique sur rotation de kid),
> `iss`, `aud` (= client_id), `exp` (leeway 60 s), `azp`, et `nonce` si fourni.
> Algorithmes asymétriques uniquement (pas de HS*/none). Garde SSRF sur toutes les URLs
> sortantes. Voir `backend/src/docflow/oidc/verify.py` + `tests/test_oidc_verify.py`
> (17 tests unitaires sans DB : mauvaise signature, iss/aud/exp/nonce/azp, alg=none).
> **Contrat frontend** : aucun appelant existant à adapter (le flow de login OIDC n'est
> pas encore câblé dans l'UI). À l'implémentation : rediriger vers l'authorization
> endpoint avec `state`+`nonce`, puis poster `{code, redirect_uri, nonce}` au callback.

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute (vérifié par relecture directe)
- **Zone** : auth / OIDC
- **Fichiers** : `backend/src/docflow/oidc/router.py:32-41` ; `backend/src/docflow/oidc/service.py:89-154`

## Description

`POST /api/auth/oidc/callback` est **public** (aucune dépendance d'auth) et accepte un dict de claims arbitraire (`body: dict[str, object]`). Il transmet ces claims tels quels à `handle_oidc_callback`, qui fait confiance à `email`/`sub` **sans aucune vérification de signature JWT**, ni appel JWKS, ni validation `issuer`/`audience`/`exp`. Le commentaire « Reçoit les claims id_token (après vérification externe) » décrit une garantie qui n'existe nulle part dans le code (aucune vérif `id_token`, `jwks`, `decode` dans `oidc/`).

## Scénario de reproduction

1. Un attaquant, sans authentification, envoie `POST /api/auth/oidc/callback` avec `{"email":"admin@local","sub":"x"}`.
2. Si un compte avec cet email (ou ce `sub`) existe, est validé et non désactivé — typiquement l'admin local créé au setup — `handle_oidc_callback` le retrouve et renvoie un **JWT docflow valide** pour ce compte.
3. Prise de contrôle totale d'un compte admin sans mot de passe.

Même sans compte existant, l'endpoint provisionne un compte (403 PendingValidation), mais l'impersonation d'un compte validé est immédiate.

## Impact

Contournement complet de l'authentification. Escalade jusqu'au compte admin. Aggravé par [AUTH-02](AUTH-02-oidc-liaison-email-sans-email-verified.md).

## Piste de correction

Le backend doit vérifier lui-même l'id_token : récupérer le JWKS de l'issuer configuré, valider signature + `iss` + `aud` (client_id) + `exp` + `nonce`, et n'accepter que des claims ainsi vérifiés. Idéalement, implémenter le flow authorization-code complet (échange du `code` côté serveur) et ne **jamais** accepter des claims bruts postés par le client.
