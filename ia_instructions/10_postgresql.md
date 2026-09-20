# PostgreSQL — migrations et accès aux données

> Fragment chargé sur déclencheur. Voir la table « Quand charger un fragment » de
> `CLAUDE.md`. **Lire avant d'écrire**, pas après.

## Quand ce document s'applique

Dès que tu t'apprêtes à écrire ou modifier une migration sous
`backend/migrations/`, ou une requête SQL.

## Conventions

- Une migration = **un fichier SQL numéroté immuable** (`0001_`, `0002_`…). On
  **n'édite jamais** une migration déjà appliquée ; on en ajoute une.
- **Réconciliation additive** : ajouter une colonne nullable est une migration
  triviale ; renommer ou supprimer exige une migration explicite et revue, jamais
  automatique.
- asyncpg : **requêtes paramétrées uniquement** (`$1..$n`). Une f-string ou un
  `.format()` dans du SQL est une faute, pas un raccourci.
- Une opération de cycle de vie = **une transaction**. Jamais d'état partiel :
  un incident en cours d'écriture ne doit pas corrompre l'existant.
- Pas d'ORM lourd : des requêtes asyncpg explicites.

## Invariants non exprimables en DDL

Cohérence `functional_type` ↔ `document`, « exactement l'un des deux »
`value` / `allowed_value_ref` au-delà du CHECK, enfant dans le même workspace que
son parent : validés **applicativement**, et **testés**. Pas en revue manuelle.

## Commandes

```bash
# apply idempotent : applique les .sql manquants dans l'ordre
cd backend && uv run python -m docflow.db.apply
```

## Pièges connus

- Une colonne ajoutée sans reprise de l'existant laisse des lignes à `NULL` : prévoir
  la lecture tolérante (`COALESCE`) **et** une reprise idempotente, par lots, une
  transaction par lot.
- Une migration testée seulement sur base vierge casse en production : la base
  existante est le cas qui compte.

## Part de checklist

- [ ] La migration s'applique **sur base vierge ET sur base existante** sans erreur
- [ ] `apply` est **idempotent** : rejoué, il ne produit aucun effet
- [ ] Aucune interpolation de chaîne dans du SQL
- [ ] Les invariants applicatifs touchés ont leur test
