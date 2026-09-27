# Tchat agents — coopération inter-agents

> Fragment déclenché — reporté du STANDARD « Fichier d'instructions agent de projet »
> (v42) le 2026-09-27. L'invariant est en synthèse dans `CLAUDE.md` ; le détail est ici.

## État réel de l'outillage — vérifié le 2026-09-27

**Les outils `tchat_*` et `agent_register` ne sont PAS servis par la gateway** de cette
session. Vérification faite côté serveur, pas seulement dans la liste cliente :
`gateway__list_backends` rend quatre backends (`workflow`, `devpod`, `doc`, `rag`), tous
`up`, et aucun n'expose ces primitives. Ce qui est disponible aujourd'hui, ce sont les
anciennes : `message_send`, `message_status`, `message_list`.

Le tchat est **porté par devpod** et reste au stade du cadrage là-bas (fiche « Cadrage —
Tchat : registre et tools `tchat_*` portés par devpod »). Ce n'est donc pas le piège du
cache d'outils client — mais **ce piège existe** et la règle tient : si `agent_register`
apparaît un jour absent alors que le cadrage est livré, ne conclus pas qu'il n'existe
pas. La liste d'outils MCP est figée à la connexion ; un outil ajouté côté portail n'y
entre qu'à la reconnexion. Vérifie côté serveur, reconnecte, et **ne substitue JAMAIS
`session_open`**.

## Ce qu'il faudra faire quand les outils seront servis

**Se rendre appelable, en début de session.** Avant de rendre la main la première fois :
`agent_register(session=<ta session tmux>, command=<ce qui t'a lancé>)`. Les deux champs
sont requis ; l'identité est **dérivée de la clé API du workspace**, jamais un paramètre
— on ne se fait pas passer pour un autre. L'outil (scope `write`) écrit le registre
déclaratif `session_agent`, signale la présence et rattrape les invitations en attente ;
il **n'exécute RIEN dans le conteneur**. Idempotent, à rejouer à chaque session.

C'est cette inscription qui fait apparaître l'agent dans le `tchat_list_agents` des
autres : la liste appelable lit ce registre, **pas** le statut « running » du workspace.
Sans inscription, personne ne peut appeler l'agent même si son workspace tourne.

Ne pas confondre avec `session_open`, outil de **spawn** (scope `exec`, lance un
`tmux new-session`, exige `workspace`) réservé au portail pour LANCER une session.
`agent_register` ne fait qu'écrire l'inscription, et c'est la primitive qu'un agent
appelle lui-même.

**Notification — JAMAIS de polling.** Quand un message attend, le marqueur exact
`[TCHAT] nouveau message` est injecté dans le stdin de la session.

**Contrat fire-and-forget.** On envoie, on ne bloque pas. Une conversation porte de la
coordination et des **références**, pas de la donnée : une conversation inactive est
ramassée par un TTL — n'y mettre rien qui doive survivre.

**Faire connaître son périmètre par un lien, pas en prose.** Le périmètre est de
l'information : il vit dans docflow, à jour. La conversation ne porte que le pointeur —
pousser dans `references` le lien vers la page « Périmètre — ce que fait docflow » du
bloc `documentation` du workspace `docflow`.

## Ce qui est retiré

L'ancienne messagerie un-à-un (spec 34 : `message_send` / `message_status` /
`message_list`) est **retirée par le standard** : ne plus la décrire comme le mécanisme
de coopération, ne plus construire de procédure dessus.

Divergence assumée, le temps que le cadrage devpod soit livré : ces outils **restent les
seuls disponibles**. S'il faut joindre un agent aujourd'hui, c'est par eux — en
consignant l'envoi et **sans jamais faire de polling sur `message_status`**, la réponse
arrivant injectée par l'utilisateur. Toute tâche bloquée se signale en fin de tour, pas
par une attente active qui gèle la session.
