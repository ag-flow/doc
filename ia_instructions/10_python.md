# Python — conventions du backend docflow

> Fragment chargé sur déclencheur. Voir la table « Quand charger un fragment » de
> `CLAUDE.md`. **Lire avant d'écrire**, pas après.

## Quand ce document s'applique

Dès que tu t'apprêtes à modifier un fichier `.py` sous `backend/`.

## Conventions

- Python 3.12+, **async/await partout** — jamais d'I/O bloquant dans un handler.
- `from __future__ import annotations` en tête de fichier ; **annotations de type partout**.
- pydantic v2, `extra="forbid"` sur tous les modèles de config et DTO d'entrée :
  **une clef inconnue est refusée, jamais ignorée en silence.**
- Journalisation structurée via `structlog.get_logger(__name__)` — **jamais** `print()`.
  Un secret ne se déballe que par `.reveal()` au point d'injection, jamais dans un log.
  `exc_info` sur tout `except` journalisé.
- **Fichiers de 300 lignes au plus** ; une responsabilité par classe ; méthodes de 5 à 15 lignes.
- Entrées utilisateur (slug, login, titre) : **validation regex stricte** avant tout
  usage en chemin, identifiant ou nom d'hôte.
- Le code ajouté **se fond dans l'existant** : même densité de commentaires, même
  nommage, mêmes idiomes que le module qui l'accueille.

## Commandes

```bash
cd backend && uv sync
cd backend && uv run uvicorn docflow.app:app --reload        # :8000
cd backend && uv run pytest -v
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format src/ tests/
cd backend && uv run mypy src/
```

## Tests

- pytest + pytest-asyncio ; fixture `client` (TestClient httpx) ; base de test
  éphémère (transaction en rollback ou base jetable).
- **TDD** : test rouge → implémentation → test vert → commit.
- Les cas de rejet sécurité sont des **tests**, pas des revues manuelles :
  anti-lock-out, slug dupliqué, isolation de workspace, secret non déballé en log.

## Pièges connus

- Charger un `.env` depuis `Settings` fait fuiter l'environnement local dans les
  tests. Le chargement d'environnement appartient aux scripts de démarrage, pas à
  la configuration.
- Un `except` sans `exc_info` perd la pile : on ne diagnostique plus rien depuis Loki.

## Part de checklist

- [ ] `uv run ruff check src/ tests/` et `uv run mypy src/` passent
- [ ] `uv run pytest` passe, et le cas nominal du changement est couvert
- [ ] Aucun fichier au-delà de 300 lignes
- [ ] Aucun secret journalisé ni déballé hors du point d'injection
