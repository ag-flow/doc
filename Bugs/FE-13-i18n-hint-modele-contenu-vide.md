# FE-13 — i18n : hint du modèle de contenu vidé par l'interpolation

- **Gravité** : 🟡 MINEUR
- **Confiance** : moyenne
- **Zone** : frontend / i18n
- **Fichiers** : `frontend/src/components/TypePropertiesPanel.tsx:181`

## Description

`t('types.contentTemplateHint', 'Variables : {{title}}, {{date}} — …')` — la clé n'existe pas dans `fr.json`, le défaut est utilisé **et interpolé** par i18next : `{{title}}`/`{{date}}` sans valeurs sont remplacés par des chaînes vides → « Variables : , — appliqué… ».

## Scénario de reproduction

Ouvrir le panneau des propriétés de type → le hint affiche des vides à la place des noms de variables.

## Impact

Message d'aide illisible (les variables à documenter disparaissent).

## Piste de correction

Ajouter une clé dédiée dans `fr.json` avec `interpolation.skipOnVariables`, ou échapper les accolades autrement.
