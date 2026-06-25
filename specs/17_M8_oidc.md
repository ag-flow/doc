# M8 — OIDC Keycloak

## Objectif

- CRUD de la config OIDC (`oidc_config`) : saisie par le bootstrap admin, une seule ligne.
- Provisioning à la volée au 1er login fédéré (match par email → remplit `oidc_subject`).
- Break-glass préservé : le password_hash de l'admin bootstrap n'est jamais écrasé.
- `client_secret_ref` stocké comme référence vault `${vault://...}`, **jamais en clair**.

## Routes exposées

| Méthode | URL | Auth |
|---------|-----|------|
| GET | `/admin/oidc` | superadmin |
| PUT | `/admin/oidc` | superadmin |
| GET | `/auth/oidc/config` | public (pour le frontend) |
| POST | `/auth/oidc/callback` | public (code OAuth2) |

## Invariants

- `client_secret_ref` jamais retourné dans les réponses API ni dans les logs (I-8).
- Si `enabled=false`, le callback OIDC est rejeté.
- Le login local (break-glass) reste toujours disponible indépendamment de l'état OIDC.
- Au provisioning : si email déjà connu → remplir `oidc_subject`, ne pas toucher `password_hash`.

## Definition of Done

- ruff + mypy propres
- Tests : CRUD oidc_config, secret non déballé en réponse/log (I-8), callback rejeté si disabled
- Login local fonctionnel même quand OIDC est configuré
