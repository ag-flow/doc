# INT-07 — `/health` fuit `str(exc)` dans la réponse 503

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : intégrations / app
- **Fichiers** : `backend/src/docflow/app.py:135`

## Description

En cas d'échec du health check, la réponse 503 renvoie `str(exc)` au client — divulgation d'un message d'erreur interne (potentiellement DSN, host, détails de connexion).

## Impact

Divulgation d'information interne sur un endpoint non authentifié.

## Piste de correction

Logger l'exception côté serveur (structlog) et renvoyer un message générique (`{"status": "unhealthy"}`) au client.
