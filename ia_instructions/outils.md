# Outils Claude Code — déclencheurs

> Fragment déclenché — texte intégral déplacé depuis `CLAUDE.md` le 2026-09-27
> (remise en forme sous le quota idéal). L'invariant est en synthèse dans
> `CLAUDE.md` ; le détail est ici, au mot près.

## Outils Claude Code

Listés **par fonction, avec leur déclencheur** : la fonction est l'invariant,
l'outil n'en est qu'une implémentation. Un outil non déclenché au bon moment ne
sert à rien.

| Fonction | Déclencheur | Outil ici |
|---|---|---|
| Doc à jour d'une bibliothèque | avant d'écrire du code qui l'utilise | **Context7** |
| Contrat réel d'une CLI | avant tout appel à une CLI externe | **`--help` first** — le binaire installé fait foi, aucune alternative |
| Navigation sémantique | avant un refactor, pour trouver les usages | **Serena** |
| Méthodes de travail | plan, exécution, débogage, TDD | **skills Superpowers** |
| Revue | >3 fichiers ou >100 lignes | **`/review`** |
| Commit | à chaque tâche livrée — obligatoire, sans attendre de demande | **`/commit`**, format français conventionnel |

Context7 ici : FastAPI, pydantic v2, asyncpg, authlib, httpx, structlog, React,
TanStack Query, Vite, Vitest, i18next, `@xyflow/react`, BlockNote, SDK MCP.
Skills : `writing-plans`, `executing-plans` / `subagent-driven-development`,
`systematic-debugging`, `test-driven-development`, `brainstorming`,
`verification-before-completion`.
