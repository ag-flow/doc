# 03 — Pièges & exigences

> Ce document liste des **exigences**, pas des conseils. Chaque point est un test ou une revue obligatoire.

## Sécurité

- **Aucun secret en clair, nulle part.** Pas dans le repo, un log, une layer Docker, une variable de build, **ni une colonne**. Le `client_secret` OIDC se stocke comme `${vault://...}` (colonne `client_secret_ref`) et ne se résout qu'au point d'usage.
- **Anti-lock-out.** Le dernier `admin_user` avec `password_hash` non null et `disabled=false` ne peut être ni désactivé ni supprimé. Toute route qui modifie un admin vérifie cet invariant **avant** d'écrire. → test dédié (désactiver le dernier admin local doit échouer).
- **fail closed.** Aucun endpoint métier sans auth. Aucune ressource d'un workspace renvoyée sans contrôle d'appartenance.
- **Validation des entrées.** `slug`, `login`, `title`, identifiants : regex stricte (`^[a-z0-9][a-z0-9_-]*$` pour les slugs) avant tout usage en requête, chemin ou clé.

## Base de données

- **Migrations immuables.** Ne jamais éditer un `000X_*.sql` déjà appliqué. Toute évolution = nouveau fichier. `apply` tient `schema_migrations` et reste **idempotent** (rejouable sans effet) → test : double `apply` ne fait rien.
- **Additif vs destructif.** Ajout de colonne nullable = OK automatique. Renommage/suppression de colonne ou table = migration explicite, revue, jamais générée à la volée par une réconciliation.
- **Requêtes paramétrées uniquement.** Une f-string/`.format()`/concaténation dans du SQL est une faille. asyncpg `$1..$n` exclusivement.
- **Transactions de lifecycle.** Une création « type + ses statuts » ou « document + ses valeurs » est **une** transaction ; un crash au milieu ne laisse pas d'état partiel. → test.

## Invariants non exprimables en DDL (donc applicatifs + testés)

1. **Enfant = même workspace que le parent** (functional_type, data_block, document). Au déplacement d'une branche, le workspace est repropagé. → test.
2. **Cohérence type ↔ valeur.** La `property_def` d'une `properties_value` doit appartenir au `functional_type` du document. → test de rejet.
3. **Exactly-one-of selon le type.** `text`/`int` ⇒ `value` renseigné, `allowed_value_ref` null. `restricted_list` ⇒ l'inverse. Le CHECK base interdit « les deux » ; l'appli interdit « le mauvais selon le type ». → test.
4. **`required` & `default_value`.** À l'écriture, une propriété `required` sans valeur est rejetée ; à la lecture, l'absence de ligne retombe sur `default_value`. → test.
5. **Contrainte miroir des data_block** (M6) : type enfant = fils direct du type parent ; racine = type racine. → test de rejet.
6. **`pattern` réservé au `text`.** Une contrainte `kind=pattern` sur une propriété `int` est refusée. Les regex sont **évaluées par l'appli**, pas par Postgres. → test.

## Slug & nommage

- Le **slug** est immuable côté usage (clé fonctionnelle) ; le **label** est libre. Le code et les templates ne pointent **jamais** le label.
- Instanciation de projets depuis un même template : **préfixer** les slugs de `data_block` (`projeta-…`) pour respecter `UNIQUE(workspace, slug)` — sinon collision immédiate.

## Auth & OIDC

- L'ordre est **non négociable** : admin local d'abord, OIDC ensuite. Aucune route ne suppose OIDC configuré pour fonctionner en mode dégradé.
- Au 1er login fédéré, on remplit `oidc_subject` sur l'`admin_user` correspondant (match par email) ou on provisionne. Ne jamais écraser un `password_hash` existant lors de ce provisioning (le break-glass survit).

## Backup

- `pg_dump` chiffré (age/gpg). Restauration testée. La sauvegarde inclut le plan d'instance (admin/OIDC) **et** le contenu — ne pas oublier qu'une restauration ramène aussi les admins.
