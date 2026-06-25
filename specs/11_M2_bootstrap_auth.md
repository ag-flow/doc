# M2 — Bootstrap auth & RBAC

**Objectif.** Seed du premier admin depuis l'env, login local argon2 → JWT, middleware
d'authentification, RBAC `admin`/`superadmin`, garde-fou anti-lock-out. Aucune logique OIDC
ici (M8) — uniquement le chemin break-glass.

**Dépend de.** M1 (pool, apply, settings, `admin_user` table via `0001_init.sql`).

---

## Périmètre

### 1 — Seed bootstrap

Au démarrage (lifespan, **après** `apply`), si `admin_user` est vide :
- Lire `ADMIN_EMAIL` et `ADMIN_PASSWORD` (déjà dans `Settings` comme `Secret`).
- Hacher le mot de passe avec argon2 (argon2-cffi, `PasswordHasher`).
- Insérer une ligne `admin_user` avec `is_superadmin=true`, `disabled=false`.
- Logger l'événement `bootstrap_admin_created` (sans révéler le mot de passe).
- Idempotent : si la table n'est pas vide, ne rien faire.

### 2 — Login local

`POST /auth/login`

Payload : `{ "email": "...", "password": "..." }`

Logique :
1. Chercher l'`admin_user` par email.
2. Rejeter si `disabled=true` ou `password_hash IS NULL`.
3. Vérifier le hash argon2 — rejeter si invalide.
4. Émettre un JWT signé avec `jwt_secret` (HS256) contenant :
   `sub` (uuid), `email`, `is_superadmin`, `iat`, `exp` (+8h).
5. Retourner `{ "access_token": "...", "token_type": "bearer" }`.

Tous les rejets renvoient HTTP 401 avec un message **non discriminant** (pas de
"email inconnu" vs "mauvais mot de passe" — message unique "identifiants invalides").

### 3 — Middleware d'authentification

Dependency FastAPI `get_current_user` :
- Extrait `Authorization: Bearer <token>`.
- Vérifie la signature JWT (HS256, `jwt_secret`).
- Vérifie `exp`.
- Recharge l'utilisateur depuis la DB (pour capter `disabled` changé depuis l'émission du token).
- Rejette si `disabled=true`.
- Retourne un `AuthUser` (DTO, pas la row asyncpg brute).

### 4 — RBAC

Deux dépendances cumulables :
- `require_admin` : utilisateur connecté et non désactivé (tout admin).
- `require_superadmin` : idem + `is_superadmin=true`.

### 5 — Gestion des admins (superadmin only)

| Méthode | Route | Description |
|---|---|---|
| GET | `/admin/users` | Liste tous les admins |
| POST | `/admin/users` | Crée un admin (label, email, password, is_superadmin) |
| GET | `/admin/users/{id}` | Détail d'un admin |
| PATCH | `/admin/users/{id}` | Modifie label, email, is_superadmin, disabled |
| DELETE | `/admin/users/{id}` | Supprime un admin |
| POST | `/admin/users/{id}/set-password` | Change le mot de passe |

### 6 — Garde-fou anti-lock-out

**Invariant** : il doit toujours exister au moins un `admin_user` avec
`password_hash IS NOT NULL AND disabled = false`.

Toute opération qui pourrait violer cet invariant (`PATCH disabled=true`, `DELETE`,
`set-password` vers `null`) doit :
1. Calculer le nombre d'admins locaux connectables **après** l'opération.
2. Si ce nombre tomberait à 0, rejeter avec HTTP 422 et code `last_local_admin`.
3. Cette vérification se fait **dans une transaction** — pas de TOCTOU.

---

## Tâches (TDD)

- [ ] `auth/seed.py` : `seed_bootstrap_admin(pool, settings)` — idempotent.
- [ ] `auth/password.py` : `hash_password(plain)`, `verify_password(plain, hash)` — argon2.
- [ ] `auth/jwt.py` : `create_token(user, secret)`, `decode_token(token, secret)` — HS256, exp 8h.
- [ ] `auth/deps.py` : `get_current_user`, `require_admin`, `require_superadmin` — deps FastAPI.
- [ ] `auth/lockout.py` : `assert_not_last_local_admin(conn, exclude_id)` — vérifié en transaction.
- [ ] `auth/router.py` : `POST /auth/login`, `GET /auth/me`.
- [ ] `admin/users/service.py` : CRUD admin_user (list, get, create, update, delete, set_password).
- [ ] `admin/users/router.py` : routes `/admin/users/*` (superadmin only).
- [ ] `schemas/auth.py` : `LoginRequest`, `TokenResponse`, `AuthUser`.
- [ ] `schemas/admin_user.py` : `AdminUserCreate`, `AdminUserUpdate`, `AdminUserOut`.
- [ ] Intégration `app.py` : appel `seed_bootstrap_admin` dans le lifespan après `apply`.
- [ ] Tests obligatoires (voir DoD).

---

## Definition of Done

1. `uv run ruff check` + `uv run mypy src/` verts.
2. `uv run pytest -v` vert, **incluant** les tests ci-dessous.
3. Bootstrap :
   - `test_seed_creates_admin_on_empty_db` — admin créé avec hash argon2 valide.
   - `test_seed_is_idempotent` — 2e appel ne crée pas de doublon.
4. Login :
   - `test_login_valid_credentials` → 200 + token JWT valide.
   - `test_login_wrong_password` → 401.
   - `test_login_unknown_email` → 401 (même message que mauvais mot de passe).
   - `test_login_disabled_user` → 401.
5. JWT & deps :
   - `test_get_me_authenticated` → 200 avec données utilisateur.
   - `test_get_me_no_token` → 401.
   - `test_get_me_expired_token` → 401.
   - `test_require_superadmin_rejects_non_superadmin` → 403.
6. Anti-lock-out :
   - `test_cannot_disable_last_local_admin` → 422 `last_local_admin`.
   - `test_cannot_delete_last_local_admin` → 422 `last_local_admin`.
   - `test_can_disable_admin_when_another_local_exists` → 200.
7. Aucun secret en clair dans un log (`ADMIN_PASSWORD` ne sort jamais).
8. Pièges `03_PITFALLS.md` cochés : anti-lock-out testé, hash argon2 (pas bcrypt), message 401 non discriminant.

---

## Notes d'implémentation

- argon2-cffi : `from argon2 import PasswordHasher; ph = PasswordHasher()`.
  `ph.hash(plain)` → stocké en DB. `ph.verify(hash, plain)` → True/False.
- JWT : utiliser `python-jose` ou `PyJWT`. **La stack impose `authlib`** — utiliser
  `authlib.jose` : `JsonWebToken`, `JWTClaims`. Vérifier l'API via Context7 avant d'écrire.
- `exp` : `iat + 8h`. Stocker en secondes epoch (int) dans le payload.
- Ne pas stocker les tokens en DB (stateless) — la révocation se fait par désactivation
  du compte (rechargé à chaque requête dans `get_current_user`).
- `updated_at` : mettre à jour à chaque PATCH via `DEFAULT now()` ou trigger — ici,
  mettre à jour applicativement dans le UPDATE.
- Consulter **Context7** pour `authlib.jose` avant d'écrire le code JWT.
