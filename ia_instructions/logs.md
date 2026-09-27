# Logs & documentation — règles intégrales

> Fragment déclenché — texte intégral déplacé depuis `CLAUDE.md` le 2026-09-27
> (remise en forme sous le quota idéal). L'invariant est en synthèse dans
> `CLAUDE.md` ; le détail est ici, au mot près.

## Logs & documentation

**Logs** : la centralisation est accessible par le service MCP (`logs_query`).

Le sélecteur de l'instance docflow est **`{host="docflow-dev", compose_service="app"}`**.
`compose_project="deploy"` seul ne suffit pas : ce label est **partagé** avec le portail
devpod (host `dev.yoops.org`, services `caddy` / `portal`) — filtrer dessus rend les
erreurs du portail et non les tiennes. `host="doc.yoops.org"` n'existe pas comme valeur
de label. Et `detected_level` n'est pas un label de flux : `{… detected_level="error"}`
rend 0 même quand des lignes d'erreur existent — filtrer sur le contenu.

**Documentation** : workspace `docflow`, bloc `Documentation` — pour lire et écrire
la doc du projet. Le cross-projet vit dans le workspace `globals`, bloc
`Documentation`. **Chaque fois que tu apprends quelque chose, écris-le en article** :
c'est ce qui alimente le RAG des agents suivants.
