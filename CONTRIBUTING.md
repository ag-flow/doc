# Contribuer à docflow

Merci de l'intérêt porté à docflow. Ce document décrit comment contribuer et le
cadre juridique des contributions.

## Licence des contributions

docflow est distribué sous la **Functional Source License 1.1 (Apache 2.0 Future
License)** — SPDX `FSL-1.1-ALv2` (voir [LICENSE](LICENSE)).

En proposant une contribution (pull request, patch, correctif), vous acceptez
que votre apport soit distribué sous cette même licence, et vous garantissez :

- que vous êtes l'auteur de la contribution, ou que vous avez le droit de la
  soumettre ;
- que vous accordez au projet le droit de la distribuer sous FSL-1.1-ALv2 (et,
  au terme du délai de bascule, sous Apache License 2.0).

Cette clause fait office de **Developer Certificate of Origin (DCO)** léger.
Signez vos commits (`git commit -s`) pour l'attester explicitement. Si un
Contributor License Agreement (CLA) formel est mis en place ultérieurement, il
sera référencé ici et prévaudra.

## Flux de travail

- Tout le développement se fait sur la branche **`dev`** (jamais `main` ni
  `feat/*` directement — cf. [CLAUDE.md](CLAUDE.md)).
- Messages de commit en **français**, format conventionnel : `feat:`, `fix:`,
  `chore:`, `docs:`, `test:`…
- Avant d'ouvrir une PR, vérifiez que la chaîne de qualité passe :

```bash
cd backend && uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest -v
cd frontend && npx tsc -b && npm run build
```

## Standard de qualité

Code propre et rigoureux, jamais de raccourci « quick & dirty ». Une tâche est
faite correctement ou pas du tout. Les invariants non exprimables en DDL, les
cas de rejet sécurité et l'anti-lock-out admin sont couverts par des **tests**,
pas par une revue manuelle. Détails dans [CLAUDE.md](CLAUDE.md).

## Signaler un bug ou une faille

Ouvrez un ticket décrivant le comportement observé, attendu, et les étapes de
reproduction. Pour une faille de sécurité, préférez un signalement privé au
mainteneur plutôt qu'un ticket public.
