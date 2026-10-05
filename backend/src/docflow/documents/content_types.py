"""Registre des types de contenu (document.type).

Valeurs stables pointées par le code et conservées en base (rétro-compat assurée).
La validation du type (absence → repli texte brut) est applicative, pas DDL.
"""

# Valeur par défaut (historique, rétro-compat assurée)
DEFAULT = "md"

# Registre déclaratif : slug → label + description.
# À élargir au fil des features MLD (F3, F5…).
CONTENT_TYPES = {
    "md": {
        "label": "Markdown",
        "description": "Contenu markdown structuré (BlockNote + syntaxe étendue).",
    },
    "table-schema": {
        "label": "Table Schema",
        "description": "Schéma de table (champs, types, relations) au format Table Schema.",
    },
    "model-layout": {
        "label": "Diagramme MLD",
        "description": "Modèle logique : nœuds (tables), ports (champs), arêtes (relations).",
    },
}


def is_valid(content_type: str | None) -> bool:
    """Vérifie qu'un type est connu et valide.

    Type None ou inconnu → retour False (le document se rend en texte brut).
    """
    return content_type is not None and content_type in CONTENT_TYPES


def label(content_type: str | None) -> str:
    """Label du type, ou fallback anonyme si type inconnu."""
    if content_type and content_type in CONTENT_TYPES:
        return CONTENT_TYPES[content_type]["label"]
    return "Contenu non reconnu"
