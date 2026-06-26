# MUI-1 — Éditeur de document (BlockNote)

**Objectif.** L'écran d'édition d'un document : titre + contenu riche, agréable à saisir, avec mermaid et images, câblé sur le write versionné `21_RW` et l'écran de conflit `ConflictResolver`.

**Dépend de.** `21_RW` (read/write contenu), `23_MTC` (le document existe, créé en deux temps), front amorcé (templates list).

## Choix d'éditeur (acté)

- **BlockNote** (MPL-2.0, gratuit pour cet usage ; aucun paquet XL requis). Style blocs façon Notion.
- **Markdown = source de vérité** : on stocke du markdown dans `document_version.content`. Conversion blocs ⇄ markdown au load/save (les helpers markdown de BlockNote).
- **Mermaid** : via le pattern `blocknote-mermaid` — un bloc custom `mermaidBlock` ; on **stocke le ` ```mermaid ` en markdown** (source canonique), on ne rend le SVG qu'à l'affichage, avec repli sur la source si le rendu échoue.
- **Images** : bloc image natif de BlockNote (upload/drag-drop). L'URL/ressource est référencée en markdown standard `![]()`.

## Cycle lecture → édition → save

1. **Load** : `GET document` → `{title, content, version}`. On parse le markdown `content` en blocs BlockNote ; `version` est mémorisée comme `expected_version`.
2. **Édition** : titre (champ simple) + corps (BlockNote). État `dirty` au premier changement.
3. **Save** : sérialiser les blocs → markdown ; `PUT {title, content, expected_version}`.
   - **200** → nouvelle `version`, on la mémorise, retour à `idle`.
   - **409** → on bascule sur l'écran **ConflictResolver** (3 volets : ancêtre = la version de base lue, serveur = contenu renvoyé par le 409, brouillon = le markdown courant). Résolution manuelle, resave sur la version serveur.
4. **Mermaid/images** : rendus à l'affichage, jamais sérialisés en SVG — le markdown reste la vérité.

## Points d'attention

- **Conversion fidèle** : valider que `markdown → blocs → markdown` est stable sur tes contenus (titres, listes, tables, code, mermaid). Tout écart de round-trip = perte ; tester tôt.
- **Sauvegarde explicite** (bouton / Cmd-S), pas d'autosave silencieux au début — l'autosave multiplierait les 409 et les versions. (Autosave possible plus tard, débattu séparément.)
- **`expected_version`** toujours issu du dernier load/save réussi, jamais deviné.

## Tâches

- [ ] Intégrer BlockNote (Vite/React/TS), thème raccord (papier froid, indigo).
- [ ] Load : `GET` + markdown→blocs ; mémoriser `expected_version`.
- [ ] Bloc mermaid custom (source markdown conservée, rendu SVG + repli).
- [ ] Bloc image (upload) → référence markdown.
- [ ] Save : blocs→markdown + `PUT` ; gestion 200/409/422.
- [ ] Branchement `ConflictResolver` sur 409 (ancêtre/serveur/brouillon).
- [ ] Tests Vitest : round-trip markdown, mapping 409→écran conflit.

## Definition of Done

1. `npm run build` (tsc strict) + Vitest verts.
2. Éditer un document, insérer un diagramme mermaid + une image, enregistrer → relire : le markdown contient bien ` ```mermaid ` et `![]()`, le rendu réapparaît.
3. Simuler un 409 → l'écran 3 volets s'ouvre avec les bons contenus, le resave sur la version serveur réussit.
4. **Context7** consulté pour BlockNote (API blocs/markdown) avant code.

## Notes

- L'éditeur ne fait que produire du markdown ; le versioning est 100 % côté `21_RW`.
- Autosave, collaboration temps réel (Yjs) : **hors scope** — ce serait un autre modèle (CRDT) que le versioning + optimistic lock retenu.
