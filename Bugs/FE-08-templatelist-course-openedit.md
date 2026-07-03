# FE-08 — TemplateList : course dans `openEdit` → mauvais YAML sauvegardé

- **Gravité** : 🟠 MAJEUR
- **Confiance** : moyenne
- **Zone** : frontend / templates
- **Fichiers** : `frontend/src/pages/TemplateList.tsx:32-43, 52-66`

## Description

`openEdit` fait un `await templatesApi.getYaml(...)` **sans garde d'annulation** ni vérification que `editTarget` n'a pas changé. Si l'utilisateur ouvre A (réponse lente), annule, puis ouvre B, la réponse tardive de A peut remplir `yamlContent` de la modale de B ; « Enregistrer » écrit alors le YAML de **A dans B**.

## Scénario de reproduction

1. Ouvrir l'édition du template A (réseau lent).
2. Fermer et ouvrir le template B.
3. La réponse de A arrive et remplit l'éditeur ; enregistrer écrase B avec le contenu de A.

## Impact

Écrasement d'un template par le contenu d'un autre en cas de réponses réseau hors-ordre.

## Piste de correction

Jeton de requête / vérifier `editTarget.template` avant `setYamlContent`.
