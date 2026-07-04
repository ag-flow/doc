# FE-16 — `/pub` non proxifié en dev

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / dev proxy
- **Fichiers** : `frontend/vite.config.ts` (proxy `/api` seulement) ; `frontend/src/lib/api.ts:314-321`

## Description

`publicApi` appelle `fetch('/pub/…')` ; en dev, Vite ne proxifie que `/api`, donc `PublicDocumentViewer` reçoit la réponse du dev-server (404/index.html) → « Document introuvable » systématique en local.

## Scénario de reproduction

En dev, ouvrir une page publique `/pub/...` → toujours « Document introuvable ».

## Impact

La visionneuse publique est intestable en dev local.

## Piste de correction

Ajouter `'/pub': 'http://localhost:8000'` au proxy Vite.
