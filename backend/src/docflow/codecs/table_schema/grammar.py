"""Vocabulaire et forme canonique du type de contenu `table-schema` (épic MLD — F5).

Base : **Table Schema** (Frictionless). Les ajouts propres à docflow sont isolés
sous le préfixe ``docflow.`` — ainsi une évolution future de la spec ne peut pas
entrer en collision avec nos extensions, et un lecteur voit d'un coup d'œil ce
qui est standard et ce qui ne l'est pas.

Règle structurante : **types LOGIQUES, jamais physiques.** Un modèle décrit ce
qu'une donnée *est* (`string`), pas comment un SGBD la range (`varchar(255)`).
Le choix physique appartient à l'implémentation, pas au modèle.
"""

from __future__ import annotations

#: Préfixe des extensions docflow (voir en-tête).
NS = "docflow."

#: Identifiant stable d'un champ / d'une relation.
ID_KEY = f"{NS}id"
#: Relations entre tables — extension docflow (`foreignKeys` de la spec ne
#: porte ni cardinalité ni libellé, et on veut un id stable par relation).
RELATIONS_KEY = f"{NS}relations"

#: Article de grammaire, cité dans chaque erreur pour que l'appelant lise la règle.
#: « 5.8 Grammaire table-schema », bloc Documentation du workspace docflow.
GRAMMAR_DOC = "docflow://doc/e29576c2-eaf7-4cc4-844c-b5db356f9dc7"

#: Types LOGIQUES acceptés. Sous-ensemble curaté de Table Schema, plus `uuid`
#: (omniprésent dans docflow) et `text` (distinction long/court, utile au MLD).
FIELD_TYPES: tuple[str, ...] = (
    "string",
    "text",
    "integer",
    "number",
    "boolean",
    "date",
    "time",
    "datetime",
    "duration",
    "uuid",
    "object",
    "array",
    "any",
)

#: Cardinalités d'une relation.
CARDINALITIES: tuple[str, ...] = (
    "one-to-one",
    "one-to-many",
    "many-to-one",
    "many-to-many",
)

#: Types physiques fréquemment écrits par réflexe, et leur équivalent logique.
#: Sert à produire un refus PÉDAGOGIQUE plutôt qu'un simple « type inconnu ».
PHYSICAL_HINTS: dict[str, str] = {
    "varchar": "string",
    "char": "string",
    "nvarchar": "string",
    "longtext": "text",
    "clob": "text",
    "int": "integer",
    "int4": "integer",
    "int8": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "serial": "integer",
    "bigserial": "integer",
    "float": "number",
    "float8": "number",
    "double": "number",
    "decimal": "number",
    "numeric": "number",
    "real": "number",
    "money": "number",
    "bool": "boolean",
    "bit": "boolean",
    "timestamp": "datetime",
    "timestamptz": "datetime",
    "datetime2": "datetime",
    "jsonb": "object",
    "json": "object",
    "blob": "any",
    "bytea": "any",
}

# ── Ordre canonique des clés ──────────────────────────────────────────────────
# La sérialisation réordonne toujours selon ces listes : deux documents de même
# sens produisent le même texte, octet pour octet. C'est ce qui rend les diffs
# lisibles et le versionnement utile.

SCHEMA_KEY_ORDER: tuple[str, ...] = (
    "name",
    "title",
    "description",
    "fields",
    "primaryKey",
    RELATIONS_KEY,
)

FIELD_KEY_ORDER: tuple[str, ...] = (
    ID_KEY,
    "name",
    "title",
    "type",
    "format",
    "description",
    "constraints",
)

RELATION_KEY_ORDER: tuple[str, ...] = (
    ID_KEY,
    "name",
    "title",
    "description",
    "cardinality",
    "from",
    "to",
)

CONSTRAINT_KEY_ORDER: tuple[str, ...] = (
    "required",
    "unique",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "enum",
)


def order_keys(mapping: dict[str, object], order: tuple[str, ...]) -> dict[str, object]:
    """Réordonne selon `order` ; les clés hors vocabulaire suivent, triées.

    Les clés inconnues ne sont pas jetées : un contenu que docflow ne comprend
    pas entièrement doit survivre à un aller-retour. Les perdre silencieusement
    détruirait du travail utilisateur.
    """
    ordered = {k: mapping[k] for k in order if k in mapping}
    rest = {k: mapping[k] for k in sorted(mapping) if k not in ordered}
    return {**ordered, **rest}
