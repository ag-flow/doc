# Recherche documentaire — règles intégrales

> Fragment déclenché — texte intégral déplacé depuis `CLAUDE.md` le 2026-09-27,
> quand le fichier a dépassé le quota idéal de ~350 lignes. Le plafond ne se relève
> pas : on remet en forme. L'invariant est énoncé en synthèse dans `CLAUDE.md`,
> le détail est ici, au mot près.

## Recherche — le RAG d'abord

**Toute recherche documentaire passe EN PRIORITÉ par le RAG**, via les primitives
`rag__*` de la gateway MCP. Le corpus y est déjà indexé et enrichi : c'est plus
rapide et plus complet qu'un `grep` sur un dépôt, et ça couvre la doc Docflow que
le système de fichiers ne contient pas.

Méthode (les noms sont ceux servis par la gateway, namespace `rag`) :

1. **`rag__list_workspaces`** — **à appeler en premier** : donne les slugs
   interrogeables et le scope de la clef. Corpus utiles ici : **`docflow-docs`
   (documentation de CE projet)**, `globals-docs` (savoir cross-projet), et un
   `<voisin>-docs` par projet voisin (`devpod-docs`, `workflow-docs`,
   `ragflow-docs`, `ressources-docs`).
2. **`rag__rag_search(workspace, query, top_k, min_score, scope)`** — recherche
   **sémantique** : question en langue naturelle, concept, intention. C'est le
   point d'entrée par défaut. `min_score` 0.3 par défaut ; monter à 0.5–0.7 pour
   une question précise. `scope='enriched_only'` pour n'interroger que les
   résumés / listes de fonctions / graphes de dépendances.
3. **`rag__search_files(workspace, pattern, mode)`** — recherche **littérale**
   quand on cherche un identifiant exact (nom de fonction, constante, chaîne) :
   `mode='exact'` par défaut (tokens entiers, ne trouve pas les sous-chaînes),
   `'substring'` pour un fragment, `'regex'` en dernier recours (lent).

Ordre de repli, pas l'inverse : RAG → si le corpus ne répond pas (sujet non
indexé, code modifié depuis l'indexation) → outils locaux (Grep/Glob/Read) ou
sous-agent Explore. Le RAG lit le contenu **indexé**, jamais les fichiers live :
pour vérifier l'état courant d'un fichier qu'on vient de modifier, lire le
fichier.

Ce que tu apprends de neuf s'écrit en article de documentation (cf. section
suivante) — c'est ce qui alimente le RAG pour les prochains agents.

**Le RAG muet n'est pas une réponse.** Le corpus ne couvre que ce qu'on y a écrit :
une route d'interface, un motif d'URL, un flag de CLI peuvent en être absents sans
que rien ne le signale — l'absence ressemble à une réponse vide, pas à une lacune.
Le repli n'est donc jamais « la documentation ne le dit pas », c'est **aller lire
l'artefact réel** : le bundle du front pour une route, `--help` pour un flag, l'API
pour une forme de réponse, le fichier lui-même pour son état courant.

Rendre un identifiant brut, un chemin approximatif ou un « je ne peux pas savoir »
alors que l'artefact est joignable, c'est renvoyer le travail à l'utilisateur.
Chercher d'abord, répondre ensuite — et si la recherche échoue vraiment, dire ce
qui a été tenté.

**Contrats d'interface** (route, webhook, event, format d'échange) : ordre propre —
documentation du projet, puis dépôt `ressources`, puis l'artefact réel.
