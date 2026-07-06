# FE-04 — Login : 401 recharge la page au lieu d'afficher l'erreur

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> L'intercepteur 401 (`lib/api.ts`) est factorisé dans `handleUnauthorized(path, hadToken)` : il ne purge le token et ne redirige vers `/login` que si un token était présent **et** que la requête ne vise pas un endpoint d'auth (`/auth/login`, `/auth/methods`, `/setup/init-admin`). Un mauvais mot de passe (POST `/auth/login`, sans token) laisse donc l'`ApiError` remonter jusqu'au `catch` de `Login.tsx`, qui affiche `t('login.error')` sans recharger la page. `Login.tsx` gérait déjà correctement l'erreur propagée — aucun changement requis côté composant.
> ⚠️ Note : la préservation du brouillon sur expiration réelle de token (session expirée en cours d'édition) n'est pas traitée ici — elle reste une redirection dure `window.location`. Une redirection routeur avec état préservé nécessiterait un handler d'auth au niveau du routeur (hors périmètre de ce correctif ciblé sur le bug de login).

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : frontend / auth
- **Fichiers** : `frontend/src/lib/api.ts:46-50, 68-72` ; `frontend/src/pages/Login.tsx:29-38` (backend `auth/router.py:45` → 401 confirmé)

## Description

L'intercepteur global 401 fait `clearToken()` + `window.location.href = '/login'` pour **toute** réponse 401, y compris le `POST /auth/login` lui-même. Un mauvais mot de passe déclenche donc un **rechargement complet** de la page de login ; `setError(t('login.error'))` n'est jamais visible. (Le cas `PendingValidation` fonctionne car le backend renvoie 403.) Effet secondaire : un token expiré pendant l'édition d'un document provoque une redirection brutale avec **perte du brouillon**.

## Scénario de reproduction

1. Saisir un mauvais mot de passe et valider.
2. La page se recharge ; aucun message d'erreur ne s'affiche.

## Impact

UX de login cassée (pas de feedback d'erreur) et perte de brouillon sur expiration de token.

## Piste de correction

Exclure les endpoints d'auth de l'intercepteur (ou ne rediriger que si un token était présent), et préférer une redirection routeur avec état préservé.
