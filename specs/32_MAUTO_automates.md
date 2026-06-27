# MAUTO — Moteur d'automates

**Objectif.** Déclencher des appels API distants quand un document **bouge** (créé/modifié), en **suivant le journal** `document_change_log` via un curseur par automate. Cas premier : réindexer un document dans agflow-rag quand il change. Paramétrage dans une page **Automates**.

**Dépend de.** `0008` (`document_change_log`, la source), `21_RW` (qui alimente le journal), le **coffre** docflow (secrets). Migrations **`0011`** (contrats), **`0012`** (automates + headers), **`0013`** (curseur + trace).

## Principe : pull par curseur (vs push webhook)

Le webhook (`29`) **pousse**, best-effort, perte possible. L'automate **tire** : un worker suit le journal à son rythme, le curseur garantit qu'aucun changement n'est manqué. C'est un **outbox de consommation**, mieux adapté à la réindexation (rattrapage garanti, pas de credit brûlé inutilement).

## Cas concret — Push Index d'ag-flow.rag

Méthode prioritaire : `POST /workspaces/{name}/index` (réindexe **un** document). Body `PushRequest` prérempli depuis le contrat, variables placées par l'utilisateur :

```json
{ "path": "{id_document}", "content": "{content}", "title": "{title}" }
```

Le contrat ne déclare **aucune auth** ni `servers:` → l'utilisateur fournit l'**URL réelle** (`https://rag…/workspaces/<rag_ws>/index`, le path `{name}` rempli en constante) et le **header d'auth** marqué secret.

## Modèle

**`openapi_contract`** (`0011`, global) : `raw_spec` (jsonb), `source_url` (refresh), `version`, `label`. Réutilisable entre workspaces.

**`automation`** (`0012`, workspace-scoped) : `label`, `active`, `on_create`/`on_update` (natures C/U), `delay_minutes` (débounce), `contract_ref` + `operation_id`, `url`, `http_method`, `body_template`.

**`automation_header`** (`0012`) : `name`, `value` **xor** `secret_ref` (modèle `WebhookHeaderIn` du RAG), `required` (du contrat), `enabled`. Le secret est résolu **à l'exécution**, jamais stocké en clair.

**`automation_cursor`** (`0013`) : `last_seq` traité par automate.

**`automation_run`** (`0013`) : `document_ref` (sans FK), `document_version`, `change_log_seq`, `status`, `UNIQUE(automation_ref, document_ref, document_version)` → **la dédup garantie par la base**.

## Contrat OpenAPI — décrire, pas remplir

- **Stockage** du contrat brut + bouton **refresh** (re-fetch depuis `source_url`, ré-écriture de `raw_spec`).
- **Parsing** → liste des opérations (method, path, summary, paramètres, schéma du body). Sélection d'une opération.
- **Formulaire plat** : on **présente** les paramètres/headers attendus (marqueur obligatoire). On valide la **présence** des obligatoires, **pas le contenu** — *« on n'est pas responsable de ce que l'utilisateur met »*.
- **Body** : squelette JSON prérempli depuis le schéma de l'opération, édité à la main dans un **éditeur JSON avec coloration syntaxique**, où l'utilisateur place les variables.

## Variables & substitution

Jeu initial (additif plus tard) : **`{id_document}`**, **`{title}`**, **`{content}`** — résolues sur la **version courante** du document au moment de l'exécution.

⚠️ Substitution **JSON-safe** : `{content}` peut contenir guillemets/sauts de ligne. On encode chaque valeur comme une chaîne JSON valide (`json.dumps`), **pas** un `str.replace` brut, sinon le premier document avec un guillemet casse le body.

## Le moteur (worker)

Boucle périodique. Pour chaque automate **actif**, lire `document_change_log` où `seq > cursor.last_seq`, `nature ∈ {C si on_create, U si on_update}`, `workspace = celui de l'automate`, par `seq` croissant. Pour chaque ligne (document D, seq S) :

1. **Version courante** V = `document.version` de D (le journal dit *qu'il faut agir*, l'action lit l'**état courant**).
2. **Dédup** : `automation_run(automate, D, V)` existe déjà ? → **skip**, avancer le curseur au-delà de S.
3. **Débounce (fenêtre glissante)** : D a-t-il une ligne de journal avec `occurred_at > now() - delay_minutes` ? → **encore chaud**, on s'arrête là (curseur non avancé au-delà de S), on retentera au prochain tick.
4. Sinon : **exécuter** (construire la requête, résoudre les secrets, substituer le body, appeler), insérer `automation_run(status, V)`, avancer le curseur.

→ **3 saves rapprochés (v6,v7,v8) = 1 seul appel** : le premier traitement réindexe la version finale V8 et écrit `run(automate,D,V8)` ; le curseur passe ensuite sur v6/v7/v8, voit V8 déjà fait, skippe. Un crédit de vectorisation, pas trois.

## Exécution

URL + méthode + headers (secrets du coffre résolus just-in-time) + body substitué JSON-safe. Timeout borné. Statut tracé (`ok`/`failed`). **Politique d'échec V1** : on trace `failed` et on **avance** le curseur (best-effort) ; rejeu manuel depuis l'historique. *(retry auto = plus tard, à décider.)*

## Page Automates (UI)

- **Contrats** : liste, import, bouton **refresh** par contrat.
- **Automates** : liste + CRUD. Formulaire : natures (C/U), `delay_minutes`, sélection **contrat + opération**, `url`, méthode, **headers** (clé / valeur, ou coche *secret* → liste des secrets du coffre), **éditeur JSON** du body avec coloration + insertion de variables.
- **Historique** : les `automation_run` (document, version, statut, heure) ; rejeu manuel d'un `failed`.

## Tâches (TDD)

- [ ] Migrations `0011`/`0012`/`0013` + `apply`.
- [ ] Stockage + parsing de contrat OpenAPI ; bouton refresh ; liste d'opérations.
- [ ] Substitution de variables **JSON-safe** (testable isolé : contenu avec guillemets/retours ligne).
- [ ] Résolution `secret_ref` → valeur via le coffre (à l'exécution).
- [ ] Worker : lecture journal par curseur, filtrage natures, **dédup par version**, **débounce glissant**, exécution, trace, avance curseur.
- [ ] Page Automates : contrats, CRUD automate, headers clé/valeur/secret, éditeur JSON, historique + rejeu.
- [ ] Tests : 3 saves → 1 appel sur version finale ; débounce ne tire qu'après calme ; secret jamais en clair ; failed tracé.

## Definition of Done

1. ruff + mypy + tests verts ; `npm run build`.
2. Import du contrat ag-flow.rag → l'opération Push Index est sélectionnable, body `{path,content,title}` prérempli.
3. Automate sur C/U avec `delay_minutes` → 3 modifs rapprochées d'un doc = **un seul** POST Push Index sur la version finale.
4. Header secret → résolu depuis le coffre à l'appel, **jamais** stocké/loggé en clair.
5. `{content}` avec guillemets → body JSON **valide** (substitution échappée).
6. Historique des runs visible ; un `failed` est rejouable.
7. **Context7** avant code (httpx async, parsing OpenAPI, asyncpg).

## Notes / décisions ouvertes

- **Référence de secret** : `secret_ref` est-il un **id** (uuid) ou un **chemin nommé** dans le coffre docflow ? (le RAG utilise un chemin/`harpo_path`). À confirmer pour figer la résolution.
- **Politique d'échec** : V1 best-effort + rejeu manuel ; retry auto à décider.
- **Head-of-line** : un document « chaud » (débounce) retarde les lignes suivantes du même automate. Acceptable en V1 (homelab) ; affinable (curseur par document) si gênant.
- **Cadence du worker** : intervalle de tick à fixer (config).
- **Natures** : `C`/`U` seulement (P jamais indexé ; `D` = reliquat → futur appel `DELETE /workspaces/{name}/index/{path}`).
- **Refresh de contrat** : si une opération référencée disparaît, signaler les automates orphelins (ne pas casser silencieusement).
