# MWH — Webhooks documents

**Objectif.** Pousser un événement vers un service externe quand un document est **créé / modifié / supprimé**. Écran de paramétrage technique (URL, headers, événements) + émission asynchrone best-effort.

**Dépend de.** `21_RW` (point d'émission sur le write), `23_MTC` (création), `28_MUI4` (écran scopé au workspace). Migration **`0007`**.

## Décisions actées

- **Livraison asynchrone, sans retry** (best-effort). Le write document **n'attend jamais** le POST ; un échec est loggé, pas réessayé. Perte d'événement sur externe down = assumée (jetable).
- **Headers chiffrés au repos** (champ chiffré, **pas** d'Harpocrate — aucune clé utilisateur ici). Clé applicative `DOCFLOW_ENCRYPTION_KEY` (env), Fernet.
- **Pas de signature HMAC.**
- **Substitution `{id_document}` seule**, dans l'**URL**.

## Frontière (dette assumée)

Aujourd'hui `url` + `headers` vivent sur l'abonnement. Le jour où la notion de **web service** sera modélisée (entité réutilisable portant base URL + auth), le hook **pointera un service** au lieu de retranscrire son auth. La décision « secret en clair vs vault » est **gelée** jusque-là. Marqué comme dette, pas comme oubli.

## Modèle (`0007`)

`webhook_subscription` scopé workspace : `id`, `workspace_technical_key`, `label`, `url`, `headers_encrypted` (JSON chiffré, nullable), `events text[]` (sous-ensemble de `document.created|updated|deleted`), `active`, timestamps. Pas d'outbox (pas de retry).

## Chiffrement

- **Fernet** (`cryptography`), clé `DOCFLOW_ENCRYPTION_KEY` en env (base64 urlsafe 32 octets), jamais commitée — même statut que le mot de passe bootstrap.
- On chiffre le **blob JSON des headers** entier au repos ; déchiffrement **uniquement à l'émission**, jamais loggé. `url` reste en clair (cible, affichable).
- Perte de clé ⇒ headers non déchiffrables ⇒ ressaisie. (Rotation de clé = hors scope.)

## Émission (couplée à `21_RW`)

- **Après commit** du write (création/màj) ou de la suppression — jamais avant : on ne notifie pas un changement non committé.
- **Best-effort fire-and-forget** : dispatch en tâche async in-process (pas d'outbox). Échec → log structuré, pas de retry, **aucun impact** sur la réponse du write.
- **Fan-out** : pour chaque `webhook_subscription` active du workspace dont `events` contient l'event → un POST. Substitution `{id_document}` dans l'URL par abonnement. **Timeout** borné par POST (ex. 8 s) pour ne pas accumuler les tâches.
- **`deleted`** : le document n'existe plus à l'émission → on **capture le snapshot** (`id`, `title`, `type`) **avant** la suppression, dans le service, et on émet après commit. Payload forcément plus maigre.

## Payload (POST, body JSON)

```json
{
  "event": "document.updated",
  "occurred_at": "2026-06-26T10:00:00Z",
  "workspace": "devpod-ui",
  "document": { "id": "{id_document}", "title": "…", "type": "feature", "version": 7 }
}
```

Pour `deleted` : `document` réduit à `{id, title, type}` (snapshot pré-suppression), pas de `version`.

## Écran de config (technique, scopé workspace)

Sous `/ws/:wsSlug/webhooks` (cohérent avec `28_MUI4`) :
- **Liste** des abonnements du workspace (label, url, events, actif).
- **Créer / éditer** : `label`, `url` (avec indice `{id_document}`), **éditeur clé-valeur** des headers, cases d'événements (`created` / `updated` / `deleted`), toggle `active`.
- **Tester** : envoie un payload synthétique à l'URL et affiche le code HTTP / l'erreur — vérification de connectivité, registre très technique.
- Headers : renvoyés **déchiffrés** à l'admin en édition (il est autorisé) ; *(à confirmer : write-only/masqué si tu préfères ne jamais réafficher)*.

## Tâches (TDD)

- [ ] Migration `0007` + `apply`.
- [ ] Helper chiffrement (Fernet, clé en config) : encrypt/decrypt headers — testable isolé.
- [ ] Service `webhook_subscription` : CRUD, validation `events` (liste fermée), scope workspace, chiffrement à l'écriture.
- [ ] Builder de payload (created/updated + snapshot deleted).
- [ ] Émission : accroche **après commit** dans les chemins write/delete de `21_RW`, fan-out, substitution `{id_document}`, timeout, fire-and-forget, log sur échec (testé avec un client HTTP factice).
- [ ] Action **Tester** (POST synthétique).
- [ ] UI : liste + créer/éditer (url, headers clé-valeur, events, active, test).

## Definition of Done

1. ruff + mypy + tests verts.
2. Abonnement sur `document.created`+`updated` d'un workspace → créer un document → l'externe reçoit un POST à l'URL avec `{id_document}` substitué et le bon payload.
3. Externe injoignable → le save du document **réussit quand même**, échec loggé, **pas** de retry.
4. `headers_encrypted` en base **n'est pas en clair** (test : la valeur stockée ≠ le JSON saisi).
5. `document.deleted` → POST avec `{id, title, type}` capturés avant suppression.
6. « Tester » renvoie le code HTTP de l'externe.
7. **Context7** avant code (cryptography/Fernet, httpx async, asyncio tasks).

## Notes / décisions ouvertes

- **Web service** : entité réutilisable à modéliser ensuite ; le hook la ciblera (auth déportée). C'est là que se rejoue « chiffré vs vault ».
- **Upgrade outbox + retry** : possible plus tard, mais touchera le point d'émission de `21_RW` (le prévoir si la fiabilité devient un besoin).
- **Filtrage par bloc/type** : aujourd'hui filtre par event seul (tout le workspace) ; affinable plus tard.
- **Réaffichage des headers** en édition : déchiffrés (défaut) vs write-only — à confirmer.
