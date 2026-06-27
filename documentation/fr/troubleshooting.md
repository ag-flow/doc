# Troubleshooting — docflow

## Sommaire

1. [L'application ne démarre pas](#1-lapplication-ne-démarre-pas)
2. [Erreur de connexion à la base de données](#2-erreur-de-connexion-à-la-base-de-données)
3. [Impossible de se connecter (login)](#3-impossible-de-se-connecter-login)
4. [Problèmes OIDC / Keycloak](#4-problèmes-oidc--keycloak)
5. [Les migrations échouent](#5-les-migrations-échouent)
6. [Les automates ne se déclenchent pas](#6-les-automates-ne-se-déclenchent-pas)
7. [Erreur lors d'une exécution d'automate](#7-erreur-lors-dune-exécution-dautomate)
8. [Secrets vault non résolus](#8-secrets-vault-non-résolus)
9. [L'image Docker ne se télécharge pas](#9-limage-docker-ne-se-télécharge-pas)
10. [Performances dégradées](#10-performances-dégradées)

---

## 1. L'application ne démarre pas

### Symptôme

Le conteneur (ou le processus) s'arrête immédiatement après le démarrage.

### Diagnostic

```bash
# Docker
docker compose -f deploy/docker-compose.prod.yml logs app

# Systemd
journalctl -u docflow -n 50
```

### Causes fréquentes

**Variable REQUIS manquante**

```
ValidationError: ... field required
```

Vérifier que toutes les variables obligatoires sont présentes dans `/data/.env` :
`DATABASE_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ENCRYPTION_KEY`.

**Port 8080 déjà utilisé**

```bash
ss -tlnp | grep 8080
```

Libérer le port ou changer le port d'écoute dans `docker-compose.prod.yml` (`"9090:8080"` par exemple).

**Fichier `.env` non trouvé**

L'application cherche les variables d'environnement via `env_file: /data/.env`. Vérifier que le fichier existe et est lisible.

```bash
ls -la /data/.env
```

---

## 2. Erreur de connexion à la base de données

### Symptôme

```
asyncpg.exceptions.ConnectionDoesNotExistError
could not connect to server: Connection refused
```

### Diagnostic

```bash
# Tester la connexion manuellement
psql "postgresql://docflow:MOT_DE_PASSE@localhost:5432/docflow" -c "SELECT 1"
```

### Causes fréquentes

**Mot de passe incorrect**

Le mot de passe dans `DATABASE_URL` doit correspondre exactement à celui de `/data/pg_password.txt` (Docker) ou au mot de passe PostgreSQL créé lors de l'installation manuelle.

**Postgres pas encore prêt (Docker)**

Le conteneur `app` démarre avant que Postgres soit prêt. Le `depends_on: condition: service_healthy` devrait prévenir ce cas, mais si le problème persiste :

```bash
docker compose -f deploy/docker-compose.prod.yml restart app
```

**Hôte incorrect**

En Docker, l'hôte doit être `postgres` (nom du service), pas `localhost`. En installation manuelle, utiliser `localhost` ou `127.0.0.1`.

**Base ou utilisateur inexistant**

```bash
# Dans psql (super-utilisateur)
\l          # lister les bases
\du         # lister les utilisateurs
```

---

## 3. Impossible de se connecter (login)

### Symptôme

Erreur « Identifiants invalides » malgré un mot de passe correct.

### Vérifications

**Vérifier que l'email est exact** (sensible à la casse).

**Compte admin non créé**

Le compte bootstrap est créé au premier démarrage. Si la base était déjà initialisée sans admin, forcer via les logs :

```bash
docker compose -f deploy/docker-compose.prod.yml logs app | grep -i "admin\|bootstrap"
```

Si absent, s'assurer que `ADMIN_EMAIL` et `ADMIN_PASSWORD` sont bien définis dans `.env`, puis redémarrer l'application.

**Token JWT expiré**

Les tokens expirent après 24 h. Se déconnecter et reconnecter.

**`JWT_SECRET` changé**

Changer `JWT_SECRET` invalide tous les tokens existants. Les utilisateurs connectés seront automatiquement redirigés vers la page de login.

---

## 4. Problèmes OIDC / Keycloak

### Le bouton OIDC n'apparaît pas

La configuration OIDC n'a pas été sauvegardée ou est invalide. Aller dans **Admin → OIDC** et vérifier que l'issuer URL, le client ID et le client secret sont renseignés.

### Erreur de callback OIDC

```
invalid_client / unauthorized_client
```

Vérifier dans Keycloak :
- Le client `docflow` existe dans le realm configuré.
- L'URL de callback `https://<domaine>/auth/oidc/callback` est dans les **Valid redirect URIs** du client Keycloak.
- Le client secret correspond à celui configuré dans docflow.

### L'utilisateur OIDC ne peut pas se connecter

Vérifier que l'utilisateur est actif dans Keycloak et que le realm est le bon (l'issuer URL contient le nom du realm).

### Client secret sous forme `${vault://…}` non résolu

Vérifier que `HARPOCRATE_URL` est défini dans `.env` et que le wallet référencé existe dans le vault.

---

## 5. Les migrations échouent

### Symptôme

L'application démarre mais les endpoints renvoient des erreurs 500, ou les logs montrent des erreurs SQL.

### Diagnostic

```bash
docker compose -f deploy/docker-compose.prod.yml logs app | grep -i "migration\|apply\|sql\|error"
```

### Causes fréquentes

**Migration déjà partiellement appliquée**

Le runner de migrations est idempotent : il ne réapplique pas une migration déjà enregistrée. Si une migration a échoué en cours, la table `schema_migrations` peut contenir un état incohérent.

```sql
-- Vérifier les migrations appliquées
SELECT * FROM schema_migrations ORDER BY applied_at;
```

**Droits insuffisants**

L'utilisateur `docflow` doit avoir les droits `CREATE TABLE`, `ALTER TABLE`, etc. sur la base `docflow`. En cas de doute :

```sql
GRANT ALL PRIVILEGES ON DATABASE docflow TO docflow;
```

**Connexion à la mauvaise base**

Vérifier que `DATABASE_URL` pointe vers la bonne base (`docflow` et non `postgres` ou autre).

---

## 6. Les automates ne se déclenchent pas

### Vérifications en ordre

1. **L'automate est-il actif ?** — Vérifier que la case **Actif** est cochée dans la configuration.

2. **Les événements sont-ils activés ?** — Au moins un des deux doit être coché : **À la création** ou **À la modification**.

3. **Le délai de débounce est-il trop long ?** — Si le délai est de 60 minutes et que la modification vient d'être faite, l'automate attend. Réduire le délai pour tester.

4. **Le worker tourne-t-il ?** — Vérifier les logs pour la mention du worker :

```bash
docker compose -f deploy/docker-compose.prod.yml logs app | grep -i "worker\|tick\|automat"
```

5. **`AUTOMATION_TICK_SECONDS`** — Par défaut 60 secondes. L'automate ne se déclenche pas instantanément ; attendre au moins un tick.

6. **Le document a-t-il été modifié après la création de l'automate ?** — L'automate ne traite que les entrées du journal de modifications (`document_change_log`) postérieures à sa création.

---

## 7. Erreur lors d'une exécution d'automate

### Voir les détails de l'exécution

Dans la page **Automates**, cliquer sur l'automate concerné pour voir l'historique. Le statut `failed` indique une erreur. Regarder les logs applicatifs au moment de l'exécution :

```bash
docker compose -f deploy/docker-compose.prod.yml logs app | grep -i "automat\|execute\|failed"
```

### Causes fréquentes

**URL injoignable**

Vérifier que l'URL de destination est accessible depuis le serveur docflow :

```bash
curl -sf <URL> -o /dev/null && echo OK || echo ERREUR
```

**Corps JSON invalide**

Si le corps contient des variables non substituées ou une syntaxe JSON incorrecte, l'exécution échoue. Tester la substitution manuellement en remplaçant `{title}`, `{content}`, `{id_document}` par des valeurs fictives.

**Timeout**

Le timeout HTTP est de 15 secondes. Si l'API de destination répond lentement, l'exécution est marquée `failed`. Rejouer depuis l'interface une fois le problème côté API corrigé.

**Header avec secret non résolu**

Si un header utilise `${vault://…}` et que Harpocrate est injoignable, l'exécution échoue. Voir [section 8](#8-secrets-vault-non-résolus).

---

## 8. Secrets vault non résolus

### Symptôme

```
Secret resolution failed / harpocrate unreachable
```

### Diagnostic

1. **`HARPOCRATE_URL` est-il défini ?**

```bash
grep HARPOCRATE_URL /data/.env
```

2. **Harpocrate est-il joignable ?**

```bash
curl -sf <HARPOCRATE_URL>/health
```

3. **Le token du wallet est-il valide ?**

Dans l'interface **Vault → Wallets**, vérifier que le wallet référencé existe et que le token n'a pas expiré.

4. **Le chemin du secret est-il correct ?**

La référence `${vault://nom_wallet:/chemin/secret}` doit correspondre exactement au wallet (`nom_wallet`) et au chemin tel qu'il est enregistré dans Harpocrate.

---

## 9. L'image Docker ne se télécharge pas

### Symptôme

```
Error response from daemon: pull access denied for ghcr.io/ag-flow/doc
```

### Solution

L'image GHCR est liée à une organisation privée. Se connecter avec un token GitHub personnel ayant la permission `read:packages` :

```bash
echo <TOKEN_GITHUB> | docker login ghcr.io -u <UTILISATEUR_GITHUB> --password-stdin
docker compose -f deploy/docker-compose.prod.yml pull
```

---

## 10. Performances dégradées

### Lenteur des requêtes

**Pool de connexions**

Le pool asyncpg est configuré pour l'usage normal. Si la charge augmente, vérifier les connexions actives :

```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'docflow';
```

**Index manquant**

Vérifier que les migrations ont toutes été appliquées (les index sont créés par les migrations).

**Logs en mode DEBUG**

Passer `LOG_LEVEL=DEBUG` augmente considérablement la quantité de logs et ralentit l'application. Revenir à `INFO` en production.

### Worker d'automates trop fréquent

Si `AUTOMATION_TICK_SECONDS` est très bas (< 10 s) avec de nombreux automates actifs, le worker peut consommer des ressources. Augmenter l'intervalle si la réactivité temps-réel n'est pas requise.
