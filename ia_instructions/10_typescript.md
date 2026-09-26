# TypeScript / frontend — conventions

> Fragment chargé sur déclencheur. Voir la table « Quand charger un fragment » de
> `CLAUDE.md`. **Lire avant d'écrire**, pas après.

## Quand ce document s'applique

Dès que tu t'apprêtes à modifier un fichier sous `frontend/src/`.

## Pile réelle

Vite + React + TypeScript **strict** + react-router-dom + TanStack Query +
Tailwind **v4** + shadcn/ui + i18next + Vitest & React Testing Library.

## Conventions

- **TypeScript strict** : pas de `any` de confort. `npx tsc -b` est le
  garde-fou — il n'y a **pas d'ESLint configuré** dans ce dépôt, ne l'invoque pas.
- Textes d'interface **toujours** via i18next (`src/locales/fr.json`), jamais en dur
  dans un composant.
- **Registre plutôt que condition** : un type de contenu se sert par une entrée de
  registre (`lib/contentSurfaces/`), jamais par un `if` chez l'appelant. Même
  principe côté backend avec les codecs — les deux registres sont des miroirs.
- **Frontières d'abstraction** : une bibliothèque de rendu (React Flow, elkjs,
  BlockNote) reste confinée à son module. Son type ne doit pas apparaître dans une
  API publique de `lib/`.
- Le code ajouté **se fond dans l'existant** : commentaires en français expliquant
  le *pourquoi*, même densité, mêmes idiomes que le fichier qui l'accueille.
- Tailwind v4 : les utilitaires gagnent sur le CSS en `@layer`, mais **perdent**
  contre le CSS non layered. Une variante de classe qui doit gagner se décide par la
  **spécificité**, jamais par l'ordre des lignes.

## Commandes

```bash
cd frontend && npm install
cd frontend && npm run dev          # :5173
cd frontend && npm run test         # vitest run
cd frontend && npx tsc -b     # types
cd frontend && npm run build        # tsc -b && vite build
```

## Tests

- Vitest + React Testing Library, dans `src/test/`. `describe` / `it` en français.
- **Un mock qui ment cache un bug.** Il doit refléter ce que l'API rend réellement :
  `listDocuments` rend des TÊTES (`content` toujours `null`), les corps se
  récupèrent document par document. Un mock qui peuple `content` sur la liste a déjà
  masqué un diagramme sans titres, sans champs et sans relations.
- Ce qui n'est pas observable au rendu sous jsdom (géométrie, mesure, choix d'un
  côté d'ancrage) se teste sur la **fonction pure** qui le décide.
- Une règle CSS qui doit gagner se teste sur la feuille produite, dans les deux sens :
  la règle attendue existe, **et** aucune formulation plus faible ne subsiste.

## Pièges connus

- Tailwind v4 a retiré `cursor: pointer` des boutons de son preflight : un élément
  cliquable doit le déclarer.
- Un `<select>` reconstruit depuis une liste d'options **perd** une valeur absente
  de cette liste au premier rendu. Une valeur inconnue se conserve et se signale.

## Part de checklist

- [ ] `npx tsc -b` passe
- [ ] `npm run test` passe, et le changement a son test
- [ ] `npm run build` passe
- [ ] Aucun texte d'interface en dur hors `locales/`
