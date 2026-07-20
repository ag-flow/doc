from __future__ import annotations

import json
import pathlib
import uuid

import asyncpg
import structlog
from mcp.server import Server
from mcp.types import TextContent, Tool

from docflow.apikeys.authz import allowed_workspace_slugs, scope_allows
from docflow.config.settings import Settings
from docflow.mcp import artifact_tools
from docflow.mcp.session import acting_identity, current_session, require_identity

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"

log = structlog.get_logger(__name__)

# Pool + settings injectés au démarrage par configure()
_pool: asyncpg.Pool | None = None
_settings: Settings | None = None

_require_identity = require_identity


_TOOLS: list[Tool] = [
    Tool(
        name="list_workspaces",
        description=(
            "Retourne la liste de tous les workspaces docflow. "
            "Chaque entrée contient : slug (clé stable à passer aux autres outils), "
            "label (nom affiché), description. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="list_types",
        description=(
            "Retourne les types fonctionnels d'un workspace (ex. epic, feature, story). "
            "Chaque type a un slug stable, un label et un éventuel parent_slug "
            "(hiérarchie). "
            "Utiliser les slugs retournés pour typer un document lors de "
            "create_document. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace (issu de list_workspaces)",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="list_documents",
        description=(
            "Retourne tous les documents d'un workspace (tous blocs confondus). "
            "Chaque entrée contient : id (UUID — clé à passer à get_document, "
            "update_document et set_property_value), title, "
            "functional_type_slug (peut être null). "
            "Liste non paginée : sur un grand workspace, privilégier une recherche "
            "ciblée. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="get_document",
        description=(
            "Lit le contenu complet d'un document : id, title, contenu (markdown "
            "brut), functional_type_slug. "
            "Ajoute 'warnings' (liste) lorsque des propriétés obligatoires du type "
            "sont non renseignées : les renseigner avec set_property_value. "
            "Retourne {error: ...} si le document n'existe pas ou n'appartient pas "
            "au workspace indiqué. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document (champ id de list_documents)",
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="create_document",
        description=(
            "Crée un document dans un bloc et le persiste immédiatement en base. "
            "ÉCRITURE : le document est visible dans l'interface et via "
            "list_documents dès la réponse. "
            "block_slug est requis : utiliser list_blocks (REST) ou lire la réponse "
            "de create_block pour obtenir le slug. "
            "Retourne l'id (UUID) et le title du document créé. "
            "functional_type_slug est optionnel mais doit correspondre au type du bloc "
            "(doit exister dans le workspace, sinon erreur). "
            "contenu est du markdown libre, optionnel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace cible"},
                "block_slug": {
                    "type": "string",
                    "description": "Slug du bloc qui contiendra le document (requis)",
                },
                "title": {"type": "string", "description": "Titre du document (non vide)"},
                "contenu": {
                    "type": "string",
                    "description": "Corps du document en markdown (optionnel)",
                },
                "functional_type_slug": {
                    "type": "string",
                    "description": (
                        "Type fonctionnel à associer (optionnel, doit exister dans le workspace)"
                    ),
                },
                "parent_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": (
                        "UUID du document parent (optionnel, même bloc) ; omis = racine du bloc"
                    ),
                },
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Valeurs initiales de propriétés : slug → valeur (pour une "
                        "restricted_list, slug de la valeur autorisée). REQUIS pour "
                        "toute propriété obligatoire sans valeur par défaut : la "
                        "création est refusée (422) sinon, avec la liste des slugs "
                        "manquants. Les propriétés à comportement automatique "
                        "(auto_now...) sont gérées par le serveur et refusées ici."
                    ),
                },
            },
            "required": ["workspace_slug", "block_slug", "title"],
        },
    ),
    Tool(
        name="update_document",
        description=(
            "Modifie le titre et/ou le contenu markdown d'un document existant. "
            "ÉCRITURE : mise à jour versionnée et permanente, visible immédiatement. "
            "Au moins un des deux champs (title ou contenu) doit être fourni, "
            "sinon erreur. "
            "La mise à jour est atomique : la version courante est lue puis "
            "incrémentée dans la même transaction (concurrence optimiste transparente). "
            "Ne touche pas au type fonctionnel ni aux valeurs de propriétés "
            "(utiliser set_property_value pour cela). "
            "Retourne {error: ...} si le document est introuvable dans le workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document à modifier",
                },
                "title": {"type": "string", "description": "Nouveau titre (omis = inchangé)"},
                "contenu": {
                    "type": "string",
                    "description": "Nouveau contenu markdown (omis = inchangé)",
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="set_document_parent",
        description=(
            "Déplace un document dans l'arborescence : définit son parent "
            "(parent_id d'un document du même bloc) ou le remonte à la racine "
            "du bloc (parent_id omis ou null). "
            "ÉCRITURE : mise à jour immédiate, sans bump de version. "
            "Contrainte de position : à la racine, le type du document doit être "
            "celui du bloc ; sous un parent, un fils direct du type du parent. "
            "Si le déplacement invalide le type actuel, l'appel échoue (422) — "
            "re-appeler en précisant functional_type_slug (nouveau type valide à "
            "la position cible) : reparentage + retypage sont alors atomiques. "
            "Les cycles sont refusés (un document ne peut devenir enfant de sa "
            "propre descendance)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document à déplacer",
                },
                "parent_id": {
                    "type": ["string", "null"],
                    "format": "uuid",
                    "description": (
                        "UUID du nouveau document parent (même bloc) ; "
                        "omis ou null = racine du bloc"
                    ),
                },
                "functional_type_slug": {
                    "type": "string",
                    "description": (
                        "Nouveau type fonctionnel à appliquer dans le même mouvement "
                        "(requis si le type actuel n'est pas valide à la position cible)"
                    ),
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="delete_document",
        description=(
            "Supprime définitivement un document. "
            "SUPPRESSION EN CASCADE : tous les documents descendants (enfants, "
            "petits-enfants, etc.) sont supprimés avec lui, ainsi que leurs valeurs "
            "de propriétés, commentaires, réactions et références sortantes vers "
            "d'autres documents. Cette cascade est irréversible. "
            "Ne supprime ni le bloc contenant le document, ni les autres documents "
            "du même bloc. "
            "GARDE : si le document a au moins un descendant, l'appel est refusé "
            "(erreur avec dependents = nombre de documents qui seraient perdus) "
            "tant que confirm=true n'est pas fourni ; relire cette valeur avant de "
            "confirmer. Un document sans descendant se supprime sans confirm. "
            "Retourne {deleted: true, id, title, type} du document supprimé "
            "(instantané capturé avant suppression) en cas de succès."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document à supprimer",
                },
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "true pour confirmer la suppression en cascade quand le "
                        "document a des descendants (défaut false ; cf. dependents "
                        "dans la réponse d'erreur pour connaître le nombre concerné)"
                    ),
                    "default": False,
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="workspace_exists",
        description=(
            "Vérifie si un workspace existe (par son slug). "
            "Ne lève jamais d'erreur si le slug est absent — retourne "
            "{exists: false}. Un workspace archivé compte comme existant "
            "(exists=true) ; utiliser list_workspaces pour distinguer les "
            "workspaces actifs des archivés. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace à vérifier",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="block_exists",
        description=(
            "Vérifie si un bloc existe (par son slug) dans un workspace. "
            "Ne lève jamais d'erreur si le workspace ou le bloc est absent — "
            "retourne {exists: false} dans les deux cas. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc à vérifier"},
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="get_block_type",
        description=(
            "Retourne le type fonctionnel d'un bloc (functional_type_slug, "
            "functional_type_label), identifié par son slug dans un workspace. "
            "Retourne {error: ...} si le workspace ou le bloc est introuvable "
            "(utiliser block_exists pour vérifier au préalable sans provoquer "
            "d'erreur). "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc"},
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="list_property_values",
        description=(
            "Retourne toutes les propriétés du type fonctionnel du document avec "
            "leur valeur actuelle (null si non renseignée). "
            "Chaque entrée contient : prop_slug, label, type "
            "(text | int | restricted_list), required (bool — obligatoire), "
            "value (texte brut pour text/int), "
            "allowed_value_slug + allowed_value_label (valeur COURANTE, pour restricted_list). "
            "Pour une restricted_list, l'entrée porte aussi allowed_values : la liste "
            "COMPLÈTE des options possibles [{slug, label}] (le jeu de valeurs varie par "
            "type fonctionnel) — utiliser ces slugs pour poser une valeur sans deviner. "
            "Une entrée required=true avec value et allowed_value_slug null est "
            "une valeur obligatoire manquante : la renseigner avec set_property_value. "
            "Utiliser prop_slug + un slug de allowed_values avec set_property_value "
            "pour écrire une valeur. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="get_property_value",
        description=(
            "Lit la valeur actuelle d'une seule propriété d'un document. "
            "Retourne : prop_slug, label, type (text | int | restricted_list), "
            "required (bool — obligatoire), value (texte brut pour text/int, null si vide), "
            "allowed_value_slug + allowed_value_label (pour restricted_list, null si vide). "
            "Préférer list_property_values pour lire toutes les propriétés d'un coup ; "
            "utiliser cet outil quand seule une propriété précise est nécessaire. "
            "Retourne {error: ...} si le document ou la propriété est introuvable. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
                "prop_slug": {
                    "type": "string",
                    "description": "Slug de la propriété à lire (issu de list_property_values)",
                },
            },
            "required": ["workspace_slug", "doc_id", "prop_slug"],
        },
    ),
    Tool(
        name="set_property_value",
        description=(
            "Écrit (crée ou remplace) la valeur d'une propriété sur un document. "
            "ÉCRITURE : upsert permanent en base, visible immédiatement dans "
            "l'interface. "
            "Règle d'exclusivité selon le type de propriété : "
            "- text ou int → fournir value (chaîne), omettre allowed_value_slug ; "
            "- restricted_list → fournir allowed_value_slug (slug de la valeur "
            "autorisée, issu de list_property_values), omettre value. "
            "Fournir les deux champs ou aucun déclenche une erreur de validation. "
            "expected_version active la concurrence optimiste : si > 0, la mise à "
            "jour échoue quand la version courante diffère (conflit concurrent). "
            "Retourne {updated: true, prop_slug} en cas de succès."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
                "prop_slug": {
                    "type": "string",
                    "description": "Slug de la propriété (issu de list_property_values)",
                },
                "value": {
                    "type": "string",
                    "description": "Valeur brute — pour propriétés text ou int uniquement",
                },
                "allowed_value_slug": {
                    "type": "string",
                    "description": (
                        "Slug de la valeur autorisée — pour propriétés restricted_list uniquement"
                    ),
                },
                "expected_version": {
                    "type": "integer",
                    "description": (
                        "Version attendue pour concurrence optimiste (0 = désactivé, défaut)"
                    ),
                    "default": 0,
                },
            },
            "required": ["workspace_slug", "doc_id", "prop_slug"],
        },
    ),
    Tool(
        name="list_templates",
        description=(
            "Retourne la liste des modèles (templates) globaux installés sur le serveur. "
            "Chaque entrée contient : template (slug stable), label, version, "
            "type_slugs (liste des types fonctionnels définis par le template). "
            "Utiliser template_slug avec import_template ou create_block pour "
            "appliquer un modèle dans un workspace. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="create_workspace",
        description=(
            "Crée un nouveau workspace docflow et le persiste immédiatement. "
            "ÉCRITURE : le workspace est visible dans l'interface dès la réponse. "
            "slug doit être unique, en minuscules, chiffres et tirets uniquement "
            "(ex. 'mon-projet-2024'). "
            "label est le nom affiché (libre). "
            "description est optionnelle. "
            "Retourne le slug, le label et le workspace_technical_key créés. "
            "Erreur 409 si le slug est déjà pris."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Identifiant unique du workspace (minuscules, tirets)",
                },
                "label": {
                    "type": "string",
                    "description": "Nom affiché du workspace",
                },
                "description": {
                    "type": "string",
                    "description": "Description optionnelle du workspace",
                },
            },
            "required": ["slug", "label"],
        },
    ),
    Tool(
        name="import_template",
        description=(
            "Importe un modèle global (issu de list_templates) dans un workspace : "
            "crée ou met à jour les types fonctionnels et leurs propriétés. "
            "ÉCRITURE : opération additive et idempotente — appeler plusieurs fois "
            "le même template sur le même workspace est sans danger. "
            "Ne supprime jamais de types existants. "
            "Retourne {applied, no_op, adds, soft_updates} : "
            "no_op=true si le workspace avait déjà la version courante du template. "
            "Erreur si workspace_slug ou template_slug est introuvable."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace cible (issu de list_workspaces)",
                },
                "template_slug": {
                    "type": "string",
                    "description": "Slug du template à importer (issu de list_templates)",
                },
            },
            "required": ["workspace_slug", "template_slug"],
        },
    ),
    Tool(
        name="create_block",
        description=(
            "Crée un bloc de données dans un workspace. "
            "ÉCRITURE : le bloc est immédiatement visible dans l'interface. "
            "functional_type_slug doit exister dans le workspace ; si template_slug "
            "est fourni, le template est importé automatiquement avant la création "
            "(idempotent — sans danger si déjà importé). "
            "slug doit être unique dans le workspace (minuscules, tirets). "
            "parent_slug est optionnel : si fourni, le bloc est enfant d'un autre bloc "
            "(contrainte miroir : le type du bloc doit être enfant du type du parent). "
            "Retourne le slug, le label et l'id du bloc créé."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace cible (issu de list_workspaces)",
                },
                "slug": {
                    "type": "string",
                    "description": "Identifiant unique du bloc dans le workspace",
                },
                "label": {
                    "type": "string",
                    "description": "Nom affiché du bloc",
                },
                "functional_type_slug": {
                    "type": "string",
                    "description": "Type fonctionnel du bloc (doit exister dans le workspace)",
                },
                "parent_slug": {
                    "type": "string",
                    "description": "Slug du bloc parent (optionnel — omis = bloc racine)",
                },
                "template_slug": {
                    "type": "string",
                    "description": (
                        "Slug d'un template global à importer avant la création "
                        "(optionnel — utile si le type n'est pas encore dans le workspace)"
                    ),
                },
            },
            "required": ["workspace_slug", "slug", "label", "functional_type_slug"],
        },
    ),
    Tool(
        name="list_blocks",
        description=(
            "Liste l'ossature complète des blocs d'un workspace. "
            "LECTURE : aucun effet de bord. "
            "Retourne pour chaque bloc : slug, label, functional_type_slug (type de "
            "sa racine), parent_slug (null si bloc racine) et exposed. "
            "À utiliser avant create_document (pour connaître les blocs et leur type) "
            "et avant delete_block, pour ne pas créer de bloc ad hoc en doublon."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace (issu de list_workspaces)",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="delete_block",
        description=(
            "Supprime un bloc d'un workspace. "
            "SUPPRESSION EN CASCADE : les blocs enfants et TOUS les documents du "
            "sous-arbre (avec leurs valeurs, versions et historique) sont détruits. "
            "Irréversible. "
            "GARDE : si le bloc a des dépendants (blocs enfants ou documents), l'appel "
            "est refusé (erreur avec child_blocks / documents / dependents) tant que "
            "confirm=true n'est pas fourni ; relire ces valeurs avant de confirmer. "
            "Un bloc vide se supprime sans confirm. "
            "Retourne {deleted: true, block_slug} en cas de succès."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace",
                },
                "block_slug": {
                    "type": "string",
                    "description": "Slug du bloc à supprimer",
                },
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "true pour confirmer la suppression en cascade quand le bloc "
                        "a des dépendants (défaut false ; cf. dependents dans la "
                        "réponse d'erreur pour connaître le nombre concerné)"
                    ),
                },
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="create_api_profile",
        description=(
            "Crée un profil d'accès API avec un périmètre limité à UN workspace. "
            "ÉCRITURE : le profil est immédiatement utilisable pour générer des clés. "
            "name doit être unique parmi les profils de l'utilisateur système. "
            "workspace_slug doit exister (utiliser list_workspaces pour le vérifier). "
            "read_only=true (défaut) : lecture seule sur tout le workspace. "
            "read_only=false : lecture et écriture sur tout le workspace. "
            "description est optionnelle. "
            "Retourne le profile_id à passer à generate_api_key."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nom unique du profil (ex. 'lecture-projet-alpha')",
                },
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace dont l'accès est accordé",
                },
                "read_only": {
                    "type": "boolean",
                    "description": "true = lecture seule (défaut), false = lecture+écriture",
                },
                "description": {
                    "type": "string",
                    "description": "Description optionnelle du profil",
                },
            },
            "required": ["name", "workspace_slug"],
        },
    ),
    Tool(
        name="generate_api_key",
        description=(
            "Génère une clé API pour un profil existant. "
            "ÉCRITURE : la clé brute (dfk_...) n'est retournée qu'une seule fois — "
            "elle ne peut pas être récupérée ultérieurement. "
            "profile_id est l'UUID retourné par create_api_profile ou list_api_profiles. "
            "label identifie l'usage de la clé (ex. 'script-ci', 'integration-x'). "
            "Retourne {key, key_prefix, profile_name} — stocker key immédiatement."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du profil (issu de create_api_profile)",
                },
                "label": {
                    "type": "string",
                    "description": "Label identifiant l'usage de la clé",
                },
            },
            "required": ["profile_id", "label"],
        },
    ),
    Tool(
        name="list_block_properties",
        description=(
            "Introspecte le schéma de propriétés d'un bloc SANS fournir de doc_id. "
            "Découverte dynamique : les slugs de propriétés (dont le statut) sont propres "
            "à chaque type fonctionnel. Retourne, pour le type racine du bloc ET ses types "
            "descendants (les seuls instanciables dans le bloc), la liste des propriétés : "
            "prop_slug, label, type (text|int|date|bool|url|float|restricted_list|reference), "
            "required, default_value ; pour restricted_list, allowed_values (slug+label). "
            "À utiliser avant set_property_value pour connaître les valeurs autorisées sans "
            "lire un document témoin. Lecture seule."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc à introspecter"},
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="list_block_objects",
        description=(
            "Liste les documents (objets) d'un bloc AVEC leurs valeurs de propriétés, "
            "en une requête et de façon PAGINÉE (page 1-based, page_size borné). Chaque "
            "objet porte id, title, functional_type_slug et la liste de ses valeurs "
            "(prop_slug, type, value pour les scalaires, allowed_value_slug/label pour les "
            "restricted_list). Évite de lire chaque document un par un. Combiner avec "
            "list_block_properties pour interpréter les valeurs. Lecture seule."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc"},
                "page": {"type": "integer", "description": "Numéro de page (1-based, défaut 1)"},
                "page_size": {
                    "type": "integer",
                    "description": "Taille de page (défaut 50, max 200)",
                },
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="query_documents",
        description=(
            "Moteur de requête PAGINÉ sur les documents d'un bloc (QuerySpec) : filtres typés, "
            "tri multi-clé, projection, sélection par type. Retourne la forme paginée de "
            "list_block_objects (total, has_next, objects avec valeurs). Lecture seule.\n"
            "- filters (rétro-compatible) : objet {prop_slug: valeur} → égalité.\n"
            "- where : liste de clauses [{prop, op, value|values}]. Opérateurs par type : "
            "text/url = eq|contains|starts_with ; int/float = eq|lt|gt|between ([min,max]) ; "
            "date = eq|before|after|between ; restricted_list = eq|in (values=[slugs]) ; "
            "bool/reference = eq. Un opérateur incompatible avec le type renvoie une erreur "
            "listant les opérateurs valides.\n"
            "- sort : liste [{key, dir}] (key = prop_slug | title | created_at ; dir = asc|desc ; "
            "restricted_list trié par ordre de pipeline).\n"
            "- projection : liste de prop_slug à remonter (défaut : toutes).\n"
            "- type_slugs : restreint aux types d'objet donnés.\n"
            "- page / page_size (défaut 50, max 100)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc"},
                "filters": {
                    "type": "object",
                    "description": "Filtre d'égalité {prop_slug: valeur} (rétro-compatible)",
                    "additionalProperties": {"type": "string"},
                },
                "where": {
                    "type": "array",
                    "description": "Clauses typées [{prop, op, value|values}]",
                    "items": {"type": "object"},
                },
                "sort": {
                    "type": "array",
                    "description": "Tri multi-clé [{key, dir}]",
                    "items": {"type": "object"},
                },
                "projection": {
                    "type": "array",
                    "description": "prop_slug à remonter (défaut : toutes)",
                    "items": {"type": "string"},
                },
                "type_slugs": {
                    "type": "array",
                    "description": "Restreindre aux types d'objet donnés",
                    "items": {"type": "string"},
                },
                "page": {"type": "integer", "description": "Numéro de page (1-based, défaut 1)"},
                "page_size": {
                    "type": "integer",
                    "description": "Taille de page (défaut 50, max 100)",
                },
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="list_block_tree",
        description=(
            "Arbre des documents d'un bloc (mode browse), PAGINÉ sur les RACINES "
            "(≤100/page). Chaque racine porte son sous-arbre complet (children récursif) "
            "et les valeurs de propriétés de chaque nœud. total/has_next comptent les "
            "racines seules : les enfants d'une racine incluse ne consomment pas le "
            "page_size. Chaque nœud : id, title, functional_type_slug, parent_id, "
            "properties, children. Lecture seule."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "block_slug": {"type": "string", "description": "Slug du bloc"},
                "page": {"type": "integer", "description": "Numéro de page (1-based, défaut 1)"},
                "page_size": {
                    "type": "integer",
                    "description": "Racines par page (défaut 50, max 100)",
                },
            },
            "required": ["workspace_slug", "block_slug"],
        },
    ),
    Tool(
        name="sync_child_documents",
        description=(
            "Synchronise en une opération d'ensemble les documents enfants d'un "
            "parent à partir d'une propriété de corrélation 'external_id'. "
            "ÉCRITURE : réconcilie une livraison (items) avec les enfants existants "
            "du parent, du type child_type_slug. "
            "Par item (external_id obligatoire) : présent en base ET dans items → "
            "update (titre/contenu/propriétés qui diffèrent) ou unchanged si rien ne "
            "change ; absent en base → create (enfant du parent). "
            "Si exhaustive=true, un enfant présent en base mais absent des items voit "
            "sa propriété 'status' passée à 'removed_at_source' (JAMAIS de "
            "suppression) → removed_marked ; s'il l'est déjà, unchanged. "
            "exhaustive=false → aucun marquage de retrait. "
            "Opération idempotente : un rejeu à l'identique n'écrit rien. "
            "Le type enfant DOIT posséder une propriété 'external_id' ; le marquage de "
            "retrait exige une propriété 'status' (restricted_list) avec une valeur "
            "autorisée 'removed_at_source' — sinon l'item concerné est reporté dans "
            "'errors' sans faire échouer l'opération. "
            "Retourne {created, updated, unchanged, removed_marked} (listes d'ids), "
            "counts (compteurs) et errors (items en échec)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "parent_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document parent dont on synchronise les enfants",
                },
                "child_type_slug": {
                    "type": "string",
                    "description": "Slug du type fonctionnel des enfants (ex. 'capture_item')",
                },
                "items": {
                    "type": "array",
                    "description": (
                        "Liste des items à synchroniser. Chaque item : external_id "
                        "(chaîne, obligatoire — clé de corrélation), title (chaîne), "
                        "contenu (chaîne markdown, optionnel), properties (objet "
                        "{slug: valeur} optionnel ; pour une restricted_list, la valeur "
                        "est le slug de la valeur autorisée)."
                    ),
                    "items": {"type": "object"},
                },
                "exhaustive": {
                    "type": "boolean",
                    "description": (
                        "true = les enfants absents des items sont marqués retirés "
                        "(status=removed_at_source) ; false (défaut) = aucun marquage"
                    ),
                    "default": False,
                },
            },
            "required": ["workspace_slug", "parent_id", "child_type_slug", "items"],
        },
    ),
    Tool(
        name="find_by_dedup_key",
        description=(
            "Recherche les documents d'un workspace par CLEF DE DÉDOUBLONNAGE. "
            "Le `text` fourni est normalisé (trim + minuscules) puis hashé en "
            "sha256 côté serveur ; retourne tous les documents dont la clef "
            "correspond (0..N — aucune unicité n'est imposée). Typiquement appelé "
            "AVANT un dépôt idempotent : un résultat vide (total=0) signifie « pas "
            "encore stocké ». Retourne {dedup_sha256, total, documents[]}. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "text": {
                    "type": "string",
                    "description": (
                        "Clef de dédoublonnage en clair (normalisée trim+minuscules "
                        "puis hashée en sha256 côté serveur)"
                    ),
                },
            },
            "required": ["workspace_slug", "text"],
        },
    ),
    Tool(
        name="set_dedup_key",
        description=(
            "Pose la CLEF DE DÉDOUBLONNAGE d'un document. Le `text` est normalisé "
            "(trim + minuscules) puis stocké sous forme de sha256 — la clef en "
            "clair n'est jamais conservée. ÉCRITURE. La clef est nullable et NON "
            "unique : poser la même valeur sur deux documents est autorisé (c'est "
            "l'appelant qui décide d'un doublon, l'application ne l'empêche pas). "
            "Un `text` vide ou omis efface la clef (remet à null). Retourne "
            "{updated, doc_id, dedup_sha256}."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
                "text": {
                    "type": "string",
                    "description": "Clef de dédoublonnage en clair ; vide ou omis = efface la clef",
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    *artifact_tools.ARTIFACT_TOOLS,
]

mcp_server = Server("docflow")


def configure(pool: asyncpg.Pool, settings: Settings | None = None) -> None:
    global _pool, _settings
    _pool = pool
    _settings = settings


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("MCP server not configured — call configure(pool)")
    return _pool


def _text(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


@mcp_server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def _list_tools() -> list[Tool]:
    return _TOOLS


# Autorisations par outil pour les sessions ouvertes par clé API : outil → écriture ?
# Le périmètre visé vient de arguments["workspace_slug"] (+ block_slug si l'outil le porte).
_WS_TOOLS: dict[str, bool] = {
    "list_types": False,
    "list_documents": False,
    "get_document": False,
    "list_property_values": False,
    "get_property_value": False,
    "create_document": True,
    "update_document": True,
    "set_document_parent": True,
    "delete_document": True,
    "sync_child_documents": True,
    "workspace_exists": False,
    "block_exists": False,
    "get_block_type": False,
    "set_property_value": True,
    "create_block": True,
    "list_blocks": False,
    "delete_block": True,
    "list_block_properties": False,
    "list_block_objects": False,
    "query_documents": False,
    "list_block_tree": False,
    "find_by_dedup_key": False,
    "set_dedup_key": True,
    **artifact_tools.ARTIFACT_WS_TOOLS,
}

# Outils structurels : réservés aux profils admin quand la session vient d'une clé API.
# create_api_profile / generate_api_key permettraient sinon à une clé scopée de
# fabriquer un profil admin et d'escalader hors de son périmètre.
_ADMIN_TOOLS = frozenset(
    {"create_workspace", "import_template", "create_api_profile", "generate_api_key"}
)


def _check_tool_authz(name: str, arguments: dict[str, object]) -> list[TextContent] | None:
    """Applique le profil de la clé API à l'outil demandé ; None = autorisé.

    Session JWT (ou profil admin) → aucune restriction, comme sur l'API REST.
    Miroir de check_api_key_scope / require_api_key_admin_write (auth/deps.py).
    """
    session = current_session()
    if session is None or session.unrestricted:
        return None
    if name in _ADMIN_TOOLS:
        return _text({"error": f"outil {name} : clé API non-admin, opération interdite"})
    if name in _WS_TOOLS:
        ws_slug = str(arguments.get("workspace_slug", ""))
        raw_block = arguments.get("block_slug")
        block_slug = str(raw_block) if raw_block else None
        assert session.api_key_scopes is not None  # unrestricted a déjà filtré None
        if not scope_allows(session.api_key_scopes, ws_slug, block_slug, _WS_TOOLS[name]):
            return _text({"error": f"outil {name} : hors du périmètre de la clé API"})
    return None


@mcp_server.call_tool()  # type: ignore[untyped-decorator]
async def _call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
    pool = _get_pool()
    log.info("mcp_call_tool", tool=name)

    denied = _check_tool_authz(name, arguments)
    if denied is not None:
        return denied

    if name == "list_workspaces":
        return await _list_workspaces(pool)
    if name == "list_types":
        return await _list_types(pool, str(arguments.get("workspace_slug", "")))
    if name == "list_documents":
        return await _list_documents(pool, str(arguments.get("workspace_slug", "")))
    if name == "get_document":
        return await _get_document(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
        )
    if name == "create_document":
        return await _create_document(pool, arguments)
    if name == "update_document":
        return await _update_document(pool, arguments)
    if name == "set_document_parent":
        return await _set_document_parent(pool, arguments)
    if name == "delete_document":
        return await _delete_document(pool, arguments)
    if name == "sync_child_documents":
        return await _sync_child_documents(pool, arguments)
    if name == "find_by_dedup_key":
        return await _find_by_dedup_key(pool, arguments)
    if name == "set_dedup_key":
        return await _set_dedup_key(pool, arguments)
    if name == "workspace_exists":
        return await _workspace_exists(pool, str(arguments.get("workspace_slug", "")))
    if name == "block_exists":
        return await _block_exists(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("block_slug", "")),
        )
    if name == "get_block_type":
        return await _get_block_type(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("block_slug", "")),
        )
    if name == "list_property_values":
        return await _list_property_values(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
        )
    if name == "get_property_value":
        return await _get_property_value(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
            str(arguments.get("prop_slug", "")),
        )
    if name == "set_property_value":
        return await _set_property_value(pool, arguments)
    if name == "list_templates":
        return await _list_templates()
    if name == "create_workspace":
        return await _create_workspace(pool, arguments)
    if name == "import_template":
        return await _import_template(pool, arguments)
    if name == "create_block":
        return await _create_block(pool, arguments)
    if name == "list_blocks":
        return await _list_blocks(pool, str(arguments.get("workspace_slug", "")))
    if name == "delete_block":
        return await _delete_block(pool, arguments)
    if name == "list_block_properties":
        return await _list_block_properties(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("block_slug", "")),
        )
    if name == "list_block_objects":
        return await _list_block_objects(pool, arguments)
    if name == "query_documents":
        return await _query_documents(pool, arguments)
    if name == "list_block_tree":
        return await _list_block_tree(pool, arguments)
    if name == "create_api_profile":
        return await _create_api_profile(pool, arguments)
    if name == "generate_api_key":
        return await _generate_api_key(pool, arguments)
    if name == "create_artifact":
        return await artifact_tools.handle_create_artifact(pool, _settings, arguments)
    if name == "get_artifact":
        return await artifact_tools.handle_get_artifact(pool, arguments)
    if name == "get_artifact_link":
        return await artifact_tools.handle_get_artifact_link(pool, _settings, arguments)
    return _text({"error": f"outil inconnu : {name}"})


async def _list_workspaces(pool: asyncpg.Pool) -> list[TextContent]:
    rows = await pool.fetch("SELECT slug, label, description FROM workspace ORDER BY slug")
    session = current_session()
    if session is not None and not session.unrestricted:
        assert session.api_key_scopes is not None
        allowed = allowed_workspace_slugs(session.api_key_scopes)
        rows = [r for r in rows if r["slug"] in allowed]
    return _text([dict(r) for r in rows])


async def _require_workspace(conn: asyncpg.Connection, ws_slug: str) -> uuid.UUID:
    wk: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
    )
    if wk is None:
        raise ValueError(f"workspace '{ws_slug}' introuvable")
    return wk


async def _required_unset_slugs(
    conn: asyncpg.Connection, wk: uuid.UUID, doc_id: uuid.UUID
) -> list[str]:
    """Slugs des propriétés *required* du type du document dont la valeur est nulle.

    Garde-fou consultatif au read : le contrat dur (422 à l'écriture, cf.
    ``assert_required_satisfied``) ne protège que les créations. Un document
    antérieur à l'ajout de la contrainte — ou dont la valeur par défaut n'a jamais
    été instanciée — peut présenter une propriété obligatoire à null. On ignore
    les propriétés à ``behavior`` (renseignées par le serveur). Le ``default_value``
    n'est PAS considéré satisfaisant ici : s'il n'a pas été matérialisé en valeur,
    le read renvoie bel et bien null et l'agent doit la renseigner.
    """
    rows = await conn.fetch(
        """
        SELECT pd.slug
        FROM properties_defs pd
        JOIN document d ON d.functional_type_ref = pd.functional_type_ref
                       AND d.workspace_technical_key = $1
                       AND d.doc_technical_key = $2
        LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                      AND pv.document_ref = d.doc_technical_key
        LEFT JOIN properties_value_version pvv
               ON pvv.property_value_ref = pv.id
              AND pvv.version_number = pv.version
        WHERE pd.required
          AND pd.behavior IS NULL
          AND pvv.value IS NULL
          AND pvv.allowed_value_ref IS NULL
        ORDER BY pd.slug
        """,
        wk,
        doc_id,
    )
    return [r["slug"] for r in rows]


async def _list_types(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT slug, label FROM functional_type "
            "WHERE workspace_technical_key = $1 ORDER BY slug",
            wk,
        )
    return _text([dict(r) for r in rows])


async def _list_documents(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT d.doc_technical_key::text AS id, d.title,
                   ft.slug AS functional_type_slug
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE d.workspace_technical_key = $1
            ORDER BY d.title
            """,
            wk,
        )
    return _text([dict(r) for r in rows])


async def _get_document(pool: asyncpg.Pool, ws_slug: str, doc_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT d.doc_technical_key::text AS id, d.title,
                   dv.content AS contenu,
                   ft.slug AS functional_type_slug
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            LEFT JOIN document_version dv
                   ON dv.document_ref = d.doc_technical_key
                  AND dv.version_number = d.version
            WHERE d.workspace_technical_key = $1
              AND d.doc_technical_key = $2
            """,
            wk,
            uuid.UUID(doc_id),
        )
        if row is None:
            return _text({"error": f"document '{doc_id}' introuvable"})
        unset = await _required_unset_slugs(conn, wk, uuid.UUID(doc_id))
    result = dict(row)
    if unset:
        result["warnings"] = [
            "propriété(s) obligatoire(s) non renseignée(s) : "
            + ", ".join(unset)
            + " — les renseigner avec set_property_value"
        ]
    return _text(result)


async def _create_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentCreate

    ws_slug = str(args.get("workspace_slug", ""))
    block_slug = str(args.get("block_slug", ""))
    title = str(args.get("title", ""))
    contenu = str(args["contenu"]) if "contenu" in args else None
    type_slug = str(args["functional_type_slug"]) if "functional_type_slug" in args else None
    try:
        parent_id = uuid.UUID(str(args["parent_id"])) if args.get("parent_id") else None
    except ValueError:
        return _text({"error": "parent_id : UUID invalide"})
    raw_props = args.get("properties")
    properties: dict[str, str] | None = None
    if raw_props is not None:
        if not isinstance(raw_props, dict):
            return _text({"error": "properties : objet {slug: valeur} attendu"})
        properties = {str(k): str(v) for k, v in raw_props.items()}

    async with pool.acquire() as conn:
        block_id: uuid.UUID | None = await conn.fetchval(
            """
            SELECT db.id FROM data_block db
            JOIN workspace w ON w.workspace_technical_key = db.workspace_technical_key
            WHERE w.slug = $1 AND db.slug = $2
            """,
            ws_slug,
            block_slug,
        )
    if block_id is None:
        return _text({"error": f"bloc '{block_slug}' introuvable dans le workspace '{ws_slug}'"})

    try:
        data = DocumentCreate(
            title=title,
            block_id=block_id,
            content=contenu,
            functional_type_slug=type_slug,
            parent_id=parent_id,
            properties=properties,
        )
        doc = await doc_svc.create_document(pool, ws_slug, data)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text({"created": True, "id": str(doc.doc_technical_key), "title": doc.title})


async def _update_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentUpdate

    ws_slug = str(args.get("workspace_slug", ""))
    doc_id_str = str(args.get("doc_id", ""))
    title = str(args["title"]) if "title" in args else None
    contenu = str(args["contenu"]) if "contenu" in args else None

    if not title and contenu is None:
        return _text({"error": "au moins title ou contenu requis"})

    doc_id = uuid.UUID(doc_id_str)

    # Lecture de la version courante pour la concurrence optimiste transparente
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        current_version: int | None = await conn.fetchval(
            "SELECT version FROM document "
            "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
            doc_id,
            wk,
        )
    if current_version is None:
        return _text({"error": f"document '{doc_id_str}' introuvable"})

    # Ne renseigner que les champs réellement fournis : un champ omis doit rester
    # « unset » (model_dump(exclude_unset=True) l'exclut) pour que le service
    # reporte sa valeur courante au lieu de l'écraser à NULL (bug MCO).
    update_fields: dict[str, object] = {"expected_version": current_version}
    if "title" in args:
        update_fields["title"] = title
    if "contenu" in args:
        update_fields["content"] = contenu

    try:
        data = DocumentUpdate(**update_fields)
        doc = await doc_svc.update_document(pool, ws_slug, doc_id, data)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text({"updated": True, "title": doc.title, "version": doc.version})


async def _set_document_parent(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentUpdate

    ws_slug = str(args.get("workspace_slug", ""))
    try:
        doc_id = uuid.UUID(str(args.get("doc_id", "")))
        raw_parent = args.get("parent_id")
        parent_id = uuid.UUID(str(raw_parent)) if raw_parent else None
    except ValueError:
        return _text({"error": "doc_id / parent_id : UUID invalide"})
    ft_slug = str(args["functional_type_slug"]) if args.get("functional_type_slug") else None

    # parent_id est TOUJOURS posé explicitement (None = racine) ; le type ne
    # l'est que s'il est fourni — update_document valide la position combinée.
    data = (
        DocumentUpdate(parent_id=parent_id, functional_type_slug=ft_slug)
        if ft_slug is not None
        else DocumentUpdate(parent_id=parent_id)
    )
    try:
        doc = await doc_svc.update_document(pool, ws_slug, doc_id, data)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "updated": True,
            "id": str(doc.doc_technical_key),
            "parent_id": str(doc.parent_id) if doc.parent_id else None,
            "functional_type_slug": doc.functional_type_slug,
        }
    )


async def _delete_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc

    ws_slug = str(args.get("workspace_slug", ""))
    try:
        doc_id = uuid.UUID(str(args.get("doc_id", "")))
    except ValueError:
        return _text({"error": "doc_id : UUID invalide"})
    confirm = bool(args.get("confirm", False))

    try:
        dependents = await doc_svc.count_document_descendants(pool, ws_slug, doc_id)
    except HTTPException as e:
        return _text({"error": e.detail})

    if dependents > 0 and not confirm:
        return _text(
            {
                "error": (
                    f"la suppression de ce document détruirait en cascade {dependents} "
                    "document(s) descendant(s) (valeurs, commentaires, réactions "
                    "compris) ; rappeler avec confirm=true pour confirmer"
                ),
                "dependents": dependents,
            }
        )

    try:
        snapshot = await doc_svc.delete_document(pool, ws_slug, doc_id)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text({"deleted": True, **snapshot})


async def _sync_child_documents(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents.sync import sync_child_documents

    ws_slug = str(args.get("workspace_slug", ""))
    child_type_slug = str(args.get("child_type_slug", ""))
    exhaustive = bool(args.get("exhaustive", False))
    try:
        parent_id = uuid.UUID(str(args.get("parent_id", "")))
    except ValueError:
        return _text({"error": "parent_id : UUID invalide"})

    raw_items = args.get("items")
    if not isinstance(raw_items, list) or not all(isinstance(i, dict) for i in raw_items):
        return _text({"error": "items : liste d'objets attendue"})

    try:
        result = await sync_child_documents(
            pool, ws_slug, parent_id, child_type_slug, raw_items, exhaustive
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


async def _find_by_dedup_key(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents.dedup import find_by_dedup_key

    ws_slug = str(args.get("workspace_slug", ""))
    text = str(args.get("text", ""))
    try:
        result = await find_by_dedup_key(pool, ws_slug, text)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


async def _set_dedup_key(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents.dedup import set_dedup_key

    ws_slug = str(args.get("workspace_slug", ""))
    try:
        doc_id = uuid.UUID(str(args.get("doc_id", "")))
    except ValueError:
        return _text({"error": "doc_id : UUID invalide"})
    raw_text = args.get("text")
    text = str(raw_text) if raw_text is not None else None
    try:
        result = await set_dedup_key(pool, ws_slug, doc_id, text)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


async def _workspace_exists(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    exists: object | None = await pool.fetchval("SELECT 1 FROM workspace WHERE slug = $1", ws_slug)
    return _text({"exists": exists is not None})


async def _block_exists(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> list[TextContent]:
    exists: object | None = await pool.fetchval(
        """
        SELECT 1 FROM data_block b
        JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
        WHERE w.slug = $1 AND b.slug = $2
        """,
        ws_slug,
        block_slug,
    )
    return _text({"exists": exists is not None})


async def _get_block_type(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> list[TextContent]:
    row = await pool.fetchrow(
        """
        SELECT ft.slug AS functional_type_slug, ft.label AS functional_type_label
        FROM data_block b
        JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
        JOIN functional_type ft ON ft.id = b.functional_type_ref
        WHERE w.slug = $1 AND b.slug = $2
        """,
        ws_slug,
        block_slug,
    )
    if row is None:
        return _text({"error": f"bloc '{block_slug}' introuvable dans le workspace '{ws_slug}'"})
    return _text(dict(row))


async def _list_property_values(pool: asyncpg.Pool, ws_slug: str, doc_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT pd.slug AS prop_slug, pd.label, pd.type, pd.required,
                   pvv.value,
                   pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                          AND pv.document_ref = d.doc_technical_key
            LEFT JOIN properties_value_version pvv
                   ON pvv.property_value_ref = pv.id
                  AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            ORDER BY pd.slug
            """,
            wk,
            uuid.UUID(doc_id),
        )
        # Ensemble COMPLET des valeurs autorisées par propriété restricted_list du
        # type du document (pas seulement la valeur courante) : un agent peut ainsi
        # découvrir les slugs cibles de set_property_value sans deviner.
        av_rows = await conn.fetch(
            """
            SELECT pd.slug AS prop_slug, pav.slug AS av_slug, pav.label AS av_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            JOIN properties_allowed_values pav ON pav.property_def_ref = pd.id
            WHERE pd.type = 'restricted_list'
            ORDER BY pd.slug, pav.position, pav.created_at
            """,
            wk,
            uuid.UUID(doc_id),
        )
    allowed_by_prop: dict[str, list[dict[str, str]]] = {}
    for r in av_rows:
        allowed_by_prop.setdefault(r["prop_slug"], []).append(
            {"slug": r["av_slug"], "label": r["av_label"]}
        )
    result: list[dict[str, object]] = []
    for r in rows:
        entry = dict(r)
        if entry["type"] == "restricted_list":
            entry["allowed_values"] = allowed_by_prop.get(r["prop_slug"], [])
        result.append(entry)
    return _text(result)


async def _get_property_value(
    pool: asyncpg.Pool, ws_slug: str, doc_id: str, prop_slug: str
) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT pd.slug AS prop_slug, pd.label, pd.type, pd.required,
                   pvv.value,
                   pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                          AND pv.document_ref = d.doc_technical_key
            LEFT JOIN properties_value_version pvv
                   ON pvv.property_value_ref = pv.id
                  AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            WHERE pd.slug = $3
            """,
            wk,
            uuid.UUID(doc_id),
            prop_slug,
        )
    if row is None:
        return _text({"error": f"propriété '{prop_slug}' introuvable sur ce document"})
    return _text(dict(row))


async def _set_property_value(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from docflow.documents import service as doc_svc
    from docflow.schemas.property_value import PropertyValueSet

    ws_slug = str(args.get("workspace_slug", ""))
    doc_id_str = str(args.get("doc_id", ""))
    prop_slug = str(args.get("prop_slug", ""))
    value = str(args["value"]) if "value" in args else None
    allowed_value_slug = str(args["allowed_value_slug"]) if "allowed_value_slug" in args else None
    expected_version = int(str(args.get("expected_version", 0)))

    data = PropertyValueSet(
        value=value, allowed_value_slug=allowed_value_slug, expected_version=expected_version
    )
    out = await doc_svc.set_property_value(pool, ws_slug, uuid.UUID(doc_id_str), prop_slug, data)
    return _text({"updated": True, "prop_slug": out.prop_slug})


async def _list_templates() -> list[TextContent]:
    import yaml

    from docflow.templates.inheritance import resolve
    from docflow.templates.models import Template

    result = []
    if _TEMPLATES_DIR.exists():
        for yaml_file in sorted(_TEMPLATES_DIR.glob("*.yaml")):
            try:
                with yaml_file.open() as f:
                    raw = yaml.safe_load(f)
                tpl = Template.model_validate(raw)
                resolved = resolve(tpl)
                result.append(
                    {
                        "template": tpl.template,
                        "label": tpl.label,
                        "version": tpl.version,
                        "type_slugs": [r.slug for r in resolved],
                    }
                )
            except Exception:
                log.warning("mcp_template_load_error", file=yaml_file.name, exc_info=True)
    return _text(result)


def _find_template(template_slug: str) -> object:
    """Charge un Template depuis le répertoire global ; lève ValueError si introuvable."""
    import yaml

    from docflow.templates.models import Template

    for yaml_file in _TEMPLATES_DIR.glob("*.yaml"):
        try:
            with yaml_file.open() as f:
                raw = yaml.safe_load(f)
            tpl = Template.model_validate(raw)
            if tpl.template == template_slug:
                return tpl
        except Exception:
            continue
    raise ValueError(f"template '{template_slug}' introuvable")


async def _create_workspace(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException
    from pydantic import ValidationError

    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc

    ws_slug = str(args.get("slug", ""))
    label = str(args.get("label", ""))
    description = str(args["description"]) if "description" in args else None

    try:
        data = WorkspaceCreate(slug=ws_slug, label=label, description=description)
        # Estampillage OBO : le workspace est attribué à l'utilisateur AGISSANT
        # (l'humain si l'OBO du portail l'a résolu, sinon l'identité de la clé).
        result = await ws_svc.create_workspace(pool, data, owner_id=acting_identity().id)
    except ValidationError as e:
        return _text({"error": e.errors(include_url=False)})
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "created": True,
            "slug": result.slug,
            "label": result.label,
            "workspace_technical_key": str(result.workspace_technical_key),
        }
    )


async def _import_template(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from docflow.templates.importer import (
        ImportConflictError,
        VersionConflictError,
        run_import,
    )

    ws_slug = str(args.get("workspace_slug", ""))
    template_slug = str(args.get("template_slug", ""))

    try:
        tpl = _find_template(template_slug)
        report = await run_import(pool, ws_slug, tpl)  # type: ignore[arg-type]
    except VersionConflictError as e:
        return _text({"error": str(e)})
    except ImportConflictError as e:
        conflicts = [{"path": i.path, "detail": i.detail} for i in e.diff.conflicts]
        return _text({"error": "conflits bloquants", "conflicts": conflicts})
    except ValueError as e:
        return _text({"error": str(e)})

    return _text(
        {
            "applied": report.applied,
            "no_op": report.no_op,
            "adds": len(report.diff.adds),
            "soft_updates": len(report.diff.soft_updates),
        }
    )


async def _create_block(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException
    from pydantic import ValidationError

    from docflow.blocks import service as block_svc
    from docflow.schemas.block import DataBlockCreate
    from docflow.templates.importer import (
        ImportConflictError,
        VersionConflictError,
        run_import,
    )

    ws_slug = str(args.get("workspace_slug", ""))
    blk_slug = str(args.get("slug", ""))
    label = str(args.get("label", ""))
    type_slug = str(args.get("functional_type_slug", ""))
    parent_slug = str(args["parent_slug"]) if "parent_slug" in args else None
    template_slug = str(args["template_slug"]) if "template_slug" in args else None

    if template_slug:
        try:
            tpl = _find_template(template_slug)
            await run_import(pool, ws_slug, tpl)  # type: ignore[arg-type]
        except VersionConflictError:
            pass  # version plus ancienne déjà installée — on continue
        except (ImportConflictError, ValueError) as e:
            return _text({"error": f"import template : {e}"})

    try:
        data = DataBlockCreate(
            slug=blk_slug,
            label=label,
            functional_type_slug=type_slug,
            parent_slug=parent_slug,
        )
        result = await block_svc.create_block(pool, ws_slug, data)
    except ValidationError as e:
        return _text({"error": e.errors(include_url=False)})
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "created": True,
            "id": str(result.id),
            "slug": result.slug,
            "label": result.label,
            "workspace_slug": result.workspace_slug,
            "functional_type_slug": result.functional_type_slug,
        }
    )


async def _list_blocks(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.blocks import service as block_svc

    try:
        blocks = await block_svc.list_blocks(pool, ws_slug)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(
        [
            {
                "slug": b.slug,
                "label": b.label,
                "functional_type_slug": b.functional_type_slug,
                "parent_slug": b.parent_slug,
                "exposed": b.exposed,
            }
            for b in blocks
        ]
    )


async def _delete_block(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.blocks import service as block_svc
    from docflow.errors import DependentsConflictError

    ws_slug = str(args.get("workspace_slug", ""))
    block_slug = str(args.get("block_slug", ""))
    confirm = bool(args.get("confirm", False))

    # Décompte préalable pour un message explicite (miroir de _delete_document).
    try:
        counts = await block_svc.count_block_dependents(pool, ws_slug, block_slug)
    except HTTPException as e:
        return _text({"error": e.detail})

    dependents = counts["child_blocks"] + counts["documents"]
    if dependents > 0 and not confirm:
        return _text(
            {
                "error": (
                    f"la suppression du bloc '{block_slug}' détruirait en cascade "
                    f"{counts['child_blocks']} bloc(s) enfant(s) et "
                    f"{counts['documents']} document(s) (valeurs et historique compris) ; "
                    "rappeler avec confirm=true pour confirmer"
                ),
                "child_blocks": counts["child_blocks"],
                "documents": counts["documents"],
                "dependents": dependents,
            }
        )

    try:
        await block_svc.delete_block(pool, ws_slug, block_slug, confirm=confirm)
    except DependentsConflictError as e:
        return _text({"error": e.detail, "dependents": e.dependents})
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text({"deleted": True, "block_slug": block_slug})


async def _list_block_properties(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str
) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.blocks.introspection import list_block_properties

    try:
        out = await list_block_properties(pool, ws_slug, block_slug)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(out.model_dump())


def _pagination_args(args: dict[str, object]) -> tuple[int, int]:
    from docflow.documents.block_query import DEFAULT_PAGE_SIZE

    page = int(str(args.get("page", 1)))
    page_size = int(str(args.get("page_size", DEFAULT_PAGE_SIZE)))
    return page, page_size


async def _list_block_objects(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents.block_query import list_block_objects

    page, page_size = _pagination_args(args)
    try:
        out = await list_block_objects(
            pool,
            str(args.get("workspace_slug", "")),
            str(args.get("block_slug", "")),
            page,
            page_size,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(out.model_dump())


async def _list_block_tree(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents.block_tree import TREE_DEFAULT_PAGE_SIZE, list_block_tree

    page = int(str(args.get("page", 1)))
    page_size = int(str(args.get("page_size", TREE_DEFAULT_PAGE_SIZE)))
    try:
        out = await list_block_tree(
            pool,
            str(args.get("workspace_slug", "")),
            str(args.get("block_slug", "")),
            page,
            page_size,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(out.model_dump())


async def _query_documents(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException
    from pydantic import ValidationError

    from docflow.documents.block_query import query_documents
    from docflow.schemas.query import FilterClause, QuerySpec, SortKey

    ws = str(args.get("workspace_slug", ""))
    block = str(args.get("block_slug", ""))
    page, page_size = _pagination_args(args)

    clauses: list[FilterClause] = []
    try:
        # Rétro-compatibilité : filters = {prop: valeur} → égalité.
        raw_filters = args.get("filters")
        if isinstance(raw_filters, dict):
            clauses += [
                FilterClause(prop=str(k), op="eq", value=str(v)) for k, v in raw_filters.items()
            ]
        # Forme riche : where = [{prop, op, value|values}].
        raw_where = args.get("where")
        if isinstance(raw_where, list):
            clauses += [FilterClause(**w) for w in raw_where if isinstance(w, dict)]
        raw_sort = args.get("sort")
        sort = (
            [SortKey(**s) for s in raw_sort if isinstance(s, dict)]
            if isinstance(raw_sort, list)
            else []
        )
        projection = args.get("projection")
        type_slugs = args.get("type_slugs")
        spec = QuerySpec(
            workspace_slug=ws,
            block_slug=block,
            type_slugs=type_slugs if isinstance(type_slugs, list) else None,
            filters=clauses,
            sort=sort,
            projection=projection if isinstance(projection, list) else None,
            page=page,
            page_size=page_size,
        )
    except ValidationError as e:
        return _text({"error": f"QuerySpec invalide : {e}"})

    try:
        out = await query_documents(pool, ws, spec)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(out.model_dump())


async def _create_api_profile(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.apikeys import service as ak_svc
    from docflow.apikeys.schemas import ApiProfileCreate, ApiProfileScopeIn

    name = str(args.get("name", ""))
    ws_slug = str(args.get("workspace_slug", ""))
    read_only = bool(args.get("read_only", True))
    description = str(args["description"]) if "description" in args else None

    # Le profil est rattaché à l'identité authentifiée de la session MCP —
    # jamais au premier superadmin système (alignement sur le parcours REST,
    # qui scope les clés à owner_id = l'appelant).
    owner_id = _require_identity().id

    try:
        profile = await ak_svc.create_profile(
            pool,
            owner_id,
            ApiProfileCreate(name=name, description=description, is_admin=False),
        )
        await ak_svc.set_scopes(
            pool,
            owner_id,
            profile.id,
            [ApiProfileScopeIn(workspace_slug=ws_slug, block_slug=None, read_only=read_only)],
        )
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "created": True,
            "profile_id": str(profile.id),
            "name": profile.name,
            "workspace_slug": ws_slug,
            "read_only": read_only,
        }
    )


async def _generate_api_key(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.apikeys import service as ak_svc
    from docflow.apikeys.schemas import ApiKeyCreate

    profile_id_str = str(args.get("profile_id", ""))
    label = str(args.get("label", ""))

    # Clé rattachée à l'appelant authentifié ; generate_key filtre déjà par
    # owner_id, donc un profil d'un autre utilisateur n'est pas exploitable.
    owner_id = _require_identity().id

    try:
        created = await ak_svc.generate_key(
            pool,
            owner_id,
            ApiKeyCreate(profile_id=uuid.UUID(profile_id_str), label=label),
        )
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "key": created.key,
            "key_prefix": created.key_prefix,
            "profile_name": created.profile_name,
            "label": created.label,
        }
    )
