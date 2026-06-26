# MUI-4 — Navigation & contexte workspace

**Objectif.** Corriger l'architecture d'information : la navigation à plat (Templates / Workspaces / Types / Documents en onglets égaux) ignore la hiérarchie du modèle et produit des écrans **hors portée**. On passe à une navigation **contextuelle** : le workspace est un contexte, pas un onglet.

**Dépend de.** 22 (blocs), 23 (arbre/création), 26 (Add/liste), le front existant (Templates/Workspaces déjà là).

## Diagnostic corrigé

Le modèle est hiérarchique (`workspace → bloc → documents` ; types scopés au workspace). Trois anomalies actuelles, **une seule cause** — un écran scopé affiché sans sa portée :
- Types fonctionnels accessibles sans workspace → un type appartient pourtant à un workspace.
- Documents / « Nouveau document » sans workspace ni bloc → 422 garanti (manque `workspace` + `data_block_ref`).
- Aucun écran de **bloc** → la portée intermédiaire est inatteignable.

## Hiérarchie d'information

```
GLOBAL (barre du haut)
  • Templates    (catalogue global)
  • Workspaces   (liste + création)

WORKSPACE (contexte, après "Ouvrir")
  • Types fonctionnels   (du workspace)
  • Blocs                (créer / assigner un type racine)   ← écran manquant
  • Documents            (choisir un bloc → arbre → Add)
```

## URL = vérité, contexte persistant = reflet

Articulation des deux choix retenus (A persistant **et** B dans l'URL) :
- **L'URL porte le workspace** (source de vérité, bookmarkable, rechargeable).
- **Le contexte persiste** à l'écran (fil d'Ariane + sous-onglets) et **se réhydrate depuis l'URL** à chaque chargement → un F5 ou un lien partagé ne perd jamais le contexte.

### Schéma de routes

```
/                                          → redirige vers /workspaces
/templates                                 → catalogue global
/workspaces                                → liste + création

/ws/:wsSlug                                → entrée → redirige vers .../documents
/ws/:wsSlug/types                          → types fonctionnels du workspace
/ws/:wsSlug/blocs                          → créer un bloc, assigner un type racine
/ws/:wsSlug/blocs/:blocSlug/documents      → arbre + Add (règle 0/1/2+, spec 23/26)
```

`:wsSlug` / `:blocSlug` = slugs **immuables** (clés stables, idéales en URL).

## Layout workspace & gardes de contexte

Un **layout** englobe toutes les routes `/ws/:wsSlug/*` :
- affiche le **fil d'Ariane** (`docflow › {workspace} › {section}`) et les sous-onglets Types / Blocs / Documents ;
- **valide le contexte au chargement** : si `wsSlug` n'existe pas ou est archivé → redirection `/workspaces` + message ; idem `blocSlug` inexistant → `/ws/:wsSlug/blocs`.

→ Conséquence : **aucun écran scopé ne peut s'afficher sans portée valide.** Les trois anomalies disparaissent par construction.

## Sélecteur de workspace (dropdown)

Dans le fil d'Ariane, le nom du workspace est un **dropdown** (façon GitHub) :
- liste les workspaces **actifs** (`archived_at IS NULL`) ;
- sélectionner un workspace → navigue vers `/ws/:autreSlug/{section courante}` en conservant la section si elle existe, sinon retombe sur `documents` ;
- une entrée « Tous les workspaces » → `/workspaces`.

## Correction explicite des anomalies

| Anomalie | Correction |
| --- | --- |
| Types sans workspace | Types = sous-onglet de `/ws/:wsSlug/*` ; connaît toujours son workspace |
| Documents hors contexte (422) | `/ws/:wsSlug/blocs/:blocSlug/documents` : `workspace` + `data_block_ref` toujours connus |
| Bloc manquant | Nouvel écran `/ws/:wsSlug/blocs` (créer + assigner type racine) |

## Tâches

- [ ] Router : routes ci-dessus + redirections (`/` → workspaces, `/ws/:wsSlug` → documents).
- [ ] Layout workspace : fil d'Ariane, sous-onglets, garde de validation (ws/bloc existants & actifs).
- [ ] Réhydratation du contexte depuis `:wsSlug` (store/loader) à chaque entrée.
- [ ] Dropdown workspace (actifs) + bascule conservant la section.
- [ ] Écran **Blocs** (liste + création, assignation type racine — cf. spec 22).
- [ ] Déplacer Types et Documents **sous** le workspace ; retirer leur accès global.
- [ ] Tests Vitest : garde redirige si ws inexistant/archivé ; F5 sur route profonde réhydrate ; bascule dropdown conserve la section.

## Definition of Done

1. `npm run build` + Vitest verts.
2. Sans workspace ouvert, `/ws/inconnu/types` → redirection `/workspaces` + message.
3. Ouvrir `devpod-ui` → fil d'Ariane visible ; Types/Blocs/Documents scopés ; F5 sur `/ws/devpod-ui/blocs` garde le contexte.
4. Documents inatteignables tant qu'aucun bloc n'est choisi ; une fois dans un bloc, « Add » ne produit plus de 422.
5. Dropdown : basculer de workspace conserve l'onglet courant.

## Notes

- C'est une **réorganisation** du front existant (Templates/Workspaces conservés ; Types/Documents déplacés). Pas de nouveau modèle backend — seulement l'écran Blocs (spec 22) et le câblage des portées.
- Vues sauvegardables, multi-workspace simultané : hors scope.
