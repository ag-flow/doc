# AUTH-02 — Liaison de compte OIDC par email sans `email_verified`
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : auth / OIDC
- **Fichiers** : `backend/src/docflow/oidc/service.py:115-139`

## Description

Quand aucun compte ne porte le `oidc_subject`, `handle_oidc_callback` rattache le compte existant dont l'**email correspond** (UPDATE `oidc_subject` + `source='oidc'`) et **hérite de son `is_admin`/`validated`**. Le claim `email_verified` n'est **jamais** contrôlé. Un IdP (ou un attaquant, cf. [AUTH-01](../AUTH-01-oidc-callback-sans-verification-signature.md)) présentant un email non vérifié prend le contrôle d'un compte local existant.

## Scénario de reproduction

1. Compte local admin `admin@local` (`validated=true`, `is_admin=true`).
2. Des claims OIDC avec `email=admin@local` et un `sub` attaquant.
3. Le compte local est lié au `sub` attaquant et un JWT admin est émis. Account takeover.

## Impact

Prise de contrôle de compte, combinée à AUTH-01 elle est immédiate et non authentifiée.

## Piste de correction

N'autoriser la liaison par email que si `email_verified` est `true` dans l'id_token **vérifié** ; sinon refuser ou exiger une liaison explicite par un admin.
