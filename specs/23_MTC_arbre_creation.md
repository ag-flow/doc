# MTC — Arbre & création de documents

**Objectif.** Créer un document à sa place dans l'arbre d'un bloc, dans le respect de la **grammaire des types**, et lire l'arbre (avec filtre préservant le chemin). C'est le pendant « structure de l'arbre » de `21_RW` (qui ne fait que lire/écrire l'existant).

**Dépend de.** `21_RW` (write versionné), `22_MDB` (bloc + `data_block_ref`), M4 (types).

## Règle unique des types-enfants autorisés

Au point d'insertion, le serveur calcule l'**ensemble des types autorisés** :

- **racine du bloc** (`parent = null`) → le type racine du bloc (`data_block.functional_type_ref`). *(cf. note multi-racines de MDB)*
- **sous un document de type T** → tous les types dont `parent = T` (ex. sous `feature` : `{story, atdd}`).

Cardinal → comportement (l'IHM s'y conforme, **le serveur l'impose**) :
- **0** → création interdite ici (feuille) → **422**.
- **1** → type implicite.
- **2+** → le type doit être fourni par l'appelant ; absent → **422** « type requis ».

## Contrainte « miroir » (garantie serveur)

À la création, le type du document doit appartenir à l'ensemble autorisé calculé ci-dessus. **Jamais** garanti par la seule IHM : un appel REST/MCP direct est validé pareil. Formellement : `type(enfant).parent == type(parent)`, et à la racine `type == data_block.functional_type_ref`.

## Création en deux temps

**Temps 1 — poser le nœud** (transaction) :
1. valider le type autorisé (règle + miroir) et le `parent?` (même bloc, même workspace) ;
2. créer `document` : `title`, `type='md'`, `functional_type_ref`, `parent`, `data_block_ref` (hérité du parent ou = bloc à la racine), `workspace_technical_key`, `version=1` ;
3. créer `document_version` v1 (`title`, `content=''`) ;
4. **instancier les valeurs par défaut** : pour chaque `properties_defs` du type ayant un `default_value` (ou `required`), créer `properties_values` (`version=1`) + `properties_value_version` v1 avec la valeur par défaut. Les `required` sans défaut sont créées « à remplir » et signalées à l'édition.

**Temps 2 — éditer** : l'ouverture du document passe par les écritures normales de `21_RW` (contenu + valeurs, write optimiste). La création ne fait pas la première vraie saisie ; elle pose la v1 et les défauts.

## Lecture de l'arbre

- **Scoping** : `WHERE data_block_ref = B` (à plat, dénormalisé). Titre dénormalisé sur `document` → **aucune jointure** pour afficher l'arbre.
- **Reconstruction** : arbre via `parent` ; ordre intra-fratrie (par `title` ou `created_at`, à fixer côté IHM).
- **Filtre préservant le chemin** : un nœud retenu garde ses **ancêtres** visibles (sinon un enfant trouvé serait orphelin à l'écran). Calcul : matcher les nœuds, puis remonter les `parent` jusqu'à la racine pour réintégrer les ancêtres. *(réalisable côté serveur ou côté front sur l'arbre déjà chargé ; MTC fournit la donnée à plat, l'algo de chemin vit côté lecture.)*

## Surface (factorisée)

| Opération | Entrée | Sortie |
| --- | --- | --- |
| types autorisés | `block_id, parent?` | `[functional_type]` (0/1/n) |
| créer document | `block_id, parent?, type?, title` | `201 {doc_id}` \| `422` |
| arbre du bloc | `block_id, filtre?` | `[{doc_id, title, type, parent}]` (chemins préservés si filtre) |

## Tâches (TDD)

- [ ] Service « types autorisés » (racine bloc / enfants de T).
- [ ] Création deux temps : validation miroir, pose nœud + v1 + défauts, héritage `data_block_ref`.
- [ ] Rejets : type non autorisé, type manquant si 2+, parent d'un autre bloc, feuille.
- [ ] Lecture arbre à plat + algo filtre-préservant-le-chemin.
- [ ] Adaptateurs REST + CLI.

## Definition of Done

1. ruff + mypy + tests verts.
2. Bloc `epic` : Add racine → crée un `epic` (implicite), v1 + statut par défaut `a_cadrer` instancié.
3. Sous une `feature` : Add sans type → **422** (story|atdd) ; Add `type=story` → OK ; Add `type=epic` → **422** (miroir).
4. Sous une `story` (feuille) : Add → **422**.
5. Filtre « done » : un `atdd` retenu garde son `feature` et son `epic` visibles.

## Notes

- La création ne versionne qu'une v1 ; toute édition ultérieure passe par `21_RW`.
- **Context7** avant le code (asyncpg, transactions).
