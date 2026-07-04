# DOC-04 — Changement de type : valeurs de propriétés orphelines conservées

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> Option retenue : **purge transactionnelle** des `properties_values` orphelines
> (celles dont la def n'appartient pas au nouveau type ; toutes si le type est retiré),
> dans la même transaction que le changement de type. Choix motivé : le refus créerait
> une impasse pour les propriétés `required` (I-4 interdit de supprimer leur valeur),
> rendant le type non modifiable. La contrainte de position (racine = type du bloc,
> enfant = fils direct du type du parent) est revalidée ; en cas de reparentage simultané,
> la validation se fait contre le parent visé.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : domaine / documents — cohérence type ↔ valeurs
- **Fichiers** : `backend/src/docflow/documents/service.py:367-372`

## Description

`update_document` permet de changer librement le `functional_type_slug` d'un document, **sans traiter les `properties_values` existantes** rattachées aux defs de l'ancien type, et **sans revalider la position** du doc dans son bloc (règle « type enfant = fils direct du type du parent »).

## Scénario de reproduction

1. Doc de type `feature` avec `statut=done`.
2. `PATCH {functional_type_slug: "epic"}` → la valeur `statut` survit en base.
3. `list_property_values` ne la montre plus (liste par defs du nouveau type), **mais** les filtres de vues (`filter_engine._add_property` matche par `pd.slug` sans contrainte de type) et `list_documents(functional_type, prop, allowed_value)` continuent de matcher dessus.

## Impact

Données fantômes : le board affiche le doc dans une colonne d'un statut qu'il n'a « plus », non supprimables via l'API (`DELETE /values/{prop}` renvoie 422 car la prop n'existe plus sur le nouveau type).

## Piste de correction

Au changement de type : soit refuser s'il existe des valeurs, soit purger/migrer explicitement les `properties_values` orphelines dans la même transaction ; revalider la contrainte de position dans le bloc.
