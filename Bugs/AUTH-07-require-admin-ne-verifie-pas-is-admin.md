# AUTH-07 — `require_admin` ne vérifie aucun droit admin

- **Gravité** : 🟠 MAJEUR (à trancher côté architecte selon la sémantique RBAC voulue)
- **Confiance** : haute sur le comportement, moyenne sur l'intention
- **Zone** : auth / RBAC — signalé par deux revues indépendantes
- **Fichiers** : `backend/src/docflow/auth/deps.py:86-87`

## Description

```python
async def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user
```

`require_admin` renvoie l'utilisateur **sans contrôler `is_admin`**, alors que `require_superadmin` (l.90-93) vérifie `is_admin`. C'est donc en réalité « utilisateur authentifié et validé ». Toutes les surfaces `/admin/...` gardées par `require_admin` — `contracts`, `remote` (points/certificats **avec secrets**), `webhooks`, `automations`, gestion de fichiers `templates` (get/put/delete YAML), `export` complet du workspace, connexion MCP — sont accessibles à **tout utilisateur validé**, pas seulement aux admins.

Les comptes OIDC sont créés `is_admin=false, validated=false` (`oidc/service.py:128-139`) ; une fois validés, ce sont des membres non-admin qui franchissent tous ces `require_admin`.

## Scénario de reproduction

Un membre validé non-admin appelle `GET /api/admin/remote/points`, gère des remote points/certificats, supprime des templates, ou exporte n'importe quel workspace.

## Impact

Selon la sémantique RBAC voulue : soit escalade de privilèges (membre → admin), soit à tout le moins un nom de dépendance trompeur qui piégera tout futur endpoint « protégé par `require_admin` ».

## Piste de correction

Si le modèle est bien admin/superadmin : faire vérifier un rôle par `require_admin`. Sinon, renommer en `require_authenticated` pour lever l'ambiguïté et confirmer explicitement que « utilisateur validé = accès admin » est voulu. Impacte directement [INT-03](fixed/INT-03-mcp-outils-ecriture-identite-superadmin.md) et [INT-06](fixed/INT-06-ssrf-urls-administrees.md).
