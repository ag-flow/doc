# Tchat agents — coopération inter-agents

> Fragment déclenché — reporté du STANDARD « Fichier d'instructions agent de projet »
> (v42) le 2026-09-27. L'invariant est en synthèse dans `CLAUDE.md` ; le détail est ici.

## État réel de l'outillage — vérifié le 2026-10-03

**Les outils `tchat_*` et `agent_register` SONT servis.** Le cadrage devpod a été livré,
et le catalogue rend leurs schémas complets : `agent_register`, `tchat_list_agents`,
`tchat_call_agent`, `tchat_invite_agent`, `tchat_push_message`, `tchat_get_conversation(s)`,
`tchat_close_conversation`.

**Ils ne sont pas appelables depuis une session CLI pour autant.** `tchat_list_agents`
répond : *« les tools tchat sont réservés à une session d'agent de workspace (clé API de
workspace requise) »*. L'identité étant **dérivée de la clé API du workspace** (voir plus
bas), une session sans cette clé n'a pas d'identité d'agent à inscrire — le refus est
cohérent, pas un incident. Conséquence pratique : **aucun canal inter-agents n'est
disponible d'ici**. Une tâche qui exige de joindre un agent se signale en fin de tour ;
elle ne se contourne ni par `session_open`, ni par un détour.

### Le piège de vérification, payé une fois

La version précédente de ce fragment concluait « non servis » sur la foi de
`gateway__list_backends`. **C'était faux, et la méthode était fausse** :
`list_backends` liste des *backends* (`workflow`, `devpod`, `doc`, `rag`) et **jamais
leurs primitives** — on ne peut rien en déduire sur la présence d'un outil.

Trois règles qui en découlent :

1. **Un outil ne se déclare absent qu'après l'avoir APPELÉ.** C'est l'artefact réel, le
   reste est de l'indice.
2. **Un refus d'autorisation n'est pas une absence.** « réservé à une session de
   workspace » dit que l'outil existe et que l'appelant n'y a pas droit — deux constats
   opposés dans leurs conséquences : le premier se signale, le second attend une livraison.
3. **La liste cliente est figée à la connexion.** Un outil ajouté côté portail n'y entre
   qu'à la reconnexion : un outil vu absent dans la liste mérite une reconnexion avant
   toute conclusion.

## Le geste, quand la session a une clé API de workspace

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
`message_list`) est **retirée par le standard** ET **retirée du catalogue** : elle n'est
plus appelable du tout. Ne plus la décrire comme le mécanisme de coopération, ne plus
construire de procédure dessus, et **ne plus l'annoncer comme canal de repli** — il n'y
en a pas.

Il n'y a donc plus de divergence à assumer : le tchat est le seul mécanisme, et il exige
une clé API de workspace. Depuis une session qui n'en a pas, **joindre un agent est
impossible** — la tâche se signale en fin de tour, jamais par une attente active qui gèle
la session.
