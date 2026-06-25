# M7 — Frontend

## Objectif

Interface admin câblée à l'API :
1. **Page Login** — formulaire email/password → POST /auth/login → JWT stocké en localStorage
2. **Page Types & Statuts** — liste des types fonctionnels d'un workspace, CRUD inline
3. **Page Arbre documents** — liste des documents d'un workspace, création

## Stack

Vite + React 18 + TypeScript strict + react-router-dom v6 + TanStack Query v5
+ Tailwind CSS v3 + shadcn/ui (composants manuels) + i18next + Vitest + @testing-library/react

## Écrans

- `/login` — formulaire, redirection vers `/workspaces/:ws/types` après login
- `/workspaces/:ws/types` — admin: CRUD types fonctionnels
- `/workspaces/:ws/documents` — admin: arbre documents

## Definition of Done

- `npm run build` sans erreur TypeScript
- Vitest : au moins un test par écran (render + formulaire)
- Token JWT envoyé dans `Authorization: Bearer` sur chaque requête API
- Déconnexion (clear localStorage) et redirection vers `/login` sur 401
- Pas de secret (VITE_API_BASE_URL seulement dans .env.example, jamais commité)
