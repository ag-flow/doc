# Ressources attribuées à l'agent

> Mémoire des ressources mises à ma disposition — **pas** des règles d'usage. Les
> règles sont dans `CLAUDE.md` § *Machines de test* ; ce fichier dit lesquelles
> j'ai, ici et maintenant. À tenir à jour à chaque notification d'attribution ou
> de reprise.

**État relevé le 2026-09-26**, par sonde réelle (`ssh`, `docker ps`, requête
Loki) et non par recopie de la documentation.

## Machines de test

| Ressource | Alias SSH | Joignable depuis ce poste | Rôle |
|---|---|---|---|
| `test1` | **absent de `~/.ssh/config`** | ✗ `Name or service not known` | Cité par `CLAUDE.md` § *Déploiement sur la VM de test* et par `deploy/DEPLOY.md` comme cible de déploiement |
| `test2` | déclaré (`100.74.13.151`) | ✗ `connect failed: No route to host` | Chromium sans interface (`browserless`) pour éprouver les IHM |

**Les deux machines nommées dans les instructions sont injoignables depuis
l'environnement de travail courant.** Ce n'est pas la même chose qu'« elles
n'existent pas » : `test2` a un alias et une adresse, la route manque. `test1`
n'a même pas d'entrée. Tant que ce tableau reste en l'état, tout déploiement
décrit dans `deploy/DEPLOY.md` doit être lancé par l'humain, pas par l'agent.

## Instance docflow déployée

| Ressource | Repère vérifié | Comment y accéder |
|---|---|---|
| Application docflow | `doc.yoops.org` | Surface **MCP** (serveur `claude-code`, namespace `doc`) — seul accès dont je dispose |
| Host de l'instance | label Loki `host="docflow-dev"`, service `compose_service="app"`, conteneur `deploy-app-1` | Pas d'accès SSH ; observable par les logs |

**Piège de nommage vérifié le 2026-09-25 :** le label Loki de l'instance est
`docflow-dev`, **pas** `doc.yoops.org` — ce dernier n'existe pas comme valeur de
label. Et `compose_project="deploy"` est **partagé** avec le portail devpod
(host `dev.yoops.org`, services `caddy` / `portal`) : une requête sur ce seul
label rend les erreurs du portail et non celles de docflow.

## Observabilité

| Ressource | Adresse | Accès |
|---|---|---|
| Loki / Grafana | `192.168.10.164:3001` | Primitive MCP `logs_query` (l'outil rend aussi un lien Grafana pré-filtré) |

`detected_level` **n'est pas un label de flux** : `{… detected_level="error"}`
rend 0 même quand des lignes d'erreur existent. Filtrer sur le contenu.

## Base de données de test

| Ressource | Adresse | Usage |
|---|---|---|
| PostgreSQL local | `postgresql://docflow:docflow@localhost:5432/docflow_test` | Tests d'intégration backend — **disponible et utilisé** |

Sans `DATABASE_URL`, les tests qui ont besoin d'une base sont sautés en silence :
la suite passe au vert sans avoir rien éprouvé. Toujours l'exporter.

## Ce que je n'ai pas

- **Collecteurs de métriques** (`alloy-metrics`) : aucun receveur OTLP joignable
  — c'est ce qui bloque le lot B de l'épic Observabilité et le standard Faro.
- **Origine de preview dédiée** (`preview.yoops.org`) : non configurée, donc
  `get_preview_link` reste indisponible sur l'instance.
