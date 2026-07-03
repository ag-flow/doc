# AUTH-08 — `decode_token` n'épingle pas la liste d'algorithmes

- **Gravité** : 🟡 MINEUR
- **Confiance** : moyenne
- **Zone** : auth / JWT
- **Fichiers** : `backend/src/docflow/auth/jwt.py:30-38`

## Description

`jwt.decode(token, key)` est appelé **sans** paramètre `algorithms` explicite. Bonne pratique : restreindre explicitement à `['HS256']`. Exploitabilité limitée ici car la clé est une OctKey symétrique (les confusions vers RS256 ou `alg=none` nécessitent un autre type de clé/registry), mais l'épinglage explicite reste requis pour un module d'auth.

## Scénario de reproduction

Défense en profondeur : si un futur refactor change le type de clé ou le registry, l'absence d'épinglage rouvre la porte à une confusion d'algorithme.

## Impact

Aujourd'hui non exploitable, mais dette de sécurité sur un module critique.

## Piste de correction

Passer explicitement `algorithms=['HS256']` (ou un `JWSRegistry` restreint) à `jwt.decode`, et exiger la présence de `exp` dans le `JWTClaimsRegistry` (`essential=True`).
