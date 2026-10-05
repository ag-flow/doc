"""Validation d'un `table-schema` (épic MLD — F5).

Principe : **toutes les erreurs d'un coup**, jamais la première seulement. Un
appelant — surtout un agent — doit pouvoir corriger en une passe. Chaque erreur
porte un chemin (`fields[2].type`), un code stable, le vocabulaire accepté quand
c'est un mot inconnu, et un pointeur vers l'article de grammaire.
"""

from __future__ import annotations

import re
from typing import Any

from docflow.codecs.base import CodecError
from docflow.codecs.table_schema import grammar, ids

#: Nom de table / champ / relation : identifiant sobre, stable dans une URL.
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,62}$")
#: `varchar(255)`, `numeric(10,2)` — on isole la base pour proposer l'équivalent logique.
_PARAMETRIC = re.compile(r"^([a-zA-Z_]+)\s*\(")


def _err(path: str, message: str, code: str, allowed: tuple[str, ...] = ()) -> CodecError:
    return CodecError(
        path=path, message=message, code=code, allowed=allowed, doc=grammar.GRAMMAR_DOC
    )


def _check_name(value: Any, path: str, errors: list[CodecError]) -> None:
    if value is None:
        errors.append(_err(path, "`name` est obligatoire.", "missing_name"))
    elif not isinstance(value, str) or not _NAME_RE.match(value):
        errors.append(
            _err(
                path,
                "`name` doit commencer par une lettre et ne contenir que "
                "lettres, chiffres et « _ » (63 caractères max).",
                "invalid_name",
            )
        )


def _check_type(value: Any, path: str, errors: list[CodecError]) -> None:
    if value is None:
        errors.append(_err(path, "`type` est obligatoire.", "missing_type", grammar.FIELD_TYPES))
        return
    if not isinstance(value, str):
        errors.append(
            _err(path, "`type` doit être une chaîne.", "invalid_type", grammar.FIELD_TYPES)
        )
        return
    if value in grammar.FIELD_TYPES:
        return

    # Refus PÉDAGOGIQUE : un type physique est une erreur fréquente et le
    # message doit enseigner la règle, pas seulement la constater.
    base = value.strip().lower()
    parametric = _PARAMETRIC.match(base)
    if parametric:
        base = parametric.group(1)
    suggestion = grammar.PHYSICAL_HINTS.get(base)
    if suggestion:
        errors.append(
            _err(
                path,
                f"« {value} » est un type PHYSIQUE. Un modèle décrit ce que la "
                f"donnée est, pas comment un SGBD la range : utiliser "
                f"« {suggestion} ».",
                "physical_type",
                grammar.FIELD_TYPES,
            )
        )
    else:
        errors.append(
            _err(path, f"type inconnu : « {value} ».", "unknown_type", grammar.FIELD_TYPES)
        )


def _check_fields(schema: dict[str, Any], errors: list[CodecError]) -> set[str]:
    """Valide `fields` et retourne les noms de champs reconnus."""
    raw = schema.get("fields")
    if raw is None:
        errors.append(_err("fields", "`fields` est obligatoire.", "missing_fields"))
        return set()
    if not isinstance(raw, list) or not raw:
        errors.append(_err("fields", "`fields` doit être une liste non vide.", "invalid_fields"))
        return set()

    names: set[str] = set()
    seen: set[str] = set()
    for i, field in enumerate(raw):
        path = f"fields[{i}]"
        if not isinstance(field, dict):
            errors.append(_err(path, "un champ doit être un objet.", "invalid_field"))
            continue
        _check_name(field.get("name"), f"{path}.name", errors)
        _check_type(field.get("type"), f"{path}.type", errors)

        name = field.get("name")
        if isinstance(name, str):
            if name in seen:
                errors.append(
                    _err(f"{path}.name", f"nom de champ dupliqué : « {name} ».", "duplicate_name")
                )
            seen.add(name)
            names.add(name)

        got_id = field.get(grammar.ID_KEY)
        if got_id is not None and not ids.is_valid(got_id):
            errors.append(
                _err(
                    f"{path}.{grammar.ID_KEY}",
                    "identifiant stable mal formé — le laisser vide pour qu'il soit alloué.",
                    "invalid_id",
                )
            )
    return names


def _check_primary_key(schema: dict[str, Any], names: set[str], errors: list[CodecError]) -> None:
    pk = schema.get("primaryKey")
    if pk is None:
        return
    columns = [pk] if isinstance(pk, str) else pk
    if not isinstance(columns, list):
        errors.append(
            _err(
                "primaryKey",
                "`primaryKey` doit être un nom ou une liste de noms.",
                "invalid_primary_key",
            )
        )
        return
    for i, col in enumerate(columns):
        if not isinstance(col, str) or (names and col not in names):
            errors.append(
                _err(
                    f"primaryKey[{i}]",
                    f"« {col} » ne correspond à aucun champ déclaré.",
                    "unknown_field_ref",
                    tuple(sorted(names)),
                )
            )


def _check_relation_side(
    side: Any, path: str, names: set[str], errors: list[CodecError], *, local: bool
) -> None:
    """Valide un bout de relation. `local` = les champs doivent exister ici."""
    if side is None:
        errors.append(_err(path, "extrémité de relation manquante.", "missing_relation_side"))
        return
    if local:
        columns = [side] if isinstance(side, str) else side
        if not isinstance(columns, list) or not columns:
            errors.append(
                _err(path, "`from` doit nommer au moins un champ.", "invalid_relation_side")
            )
            return
        for i, col in enumerate(columns):
            if not isinstance(col, str) or (names and col not in names):
                errors.append(
                    _err(
                        f"{path}[{i}]",
                        f"« {col} » ne correspond à aucun champ déclaré.",
                        "unknown_field_ref",
                        tuple(sorted(names)),
                    )
                )
        return
    # `to` pointe une AUTRE table : on ne peut pas vérifier ses champs ici (ils
    # vivent dans un autre document). On vérifie seulement la forme.
    if not isinstance(side, dict):
        errors.append(
            _err(path, "`to` doit porter `resource` et `fields`.", "invalid_relation_side")
        )
        return
    if not isinstance(side.get("resource"), str):
        errors.append(_err(f"{path}.resource", "`resource` est obligatoire.", "missing_resource"))
    target = side.get("fields")
    if not isinstance(target, (str, list)) or (isinstance(target, list) and not target):
        errors.append(
            _err(f"{path}.fields", "`fields` est obligatoire.", "missing_relation_fields")
        )


def _check_relations(schema: dict[str, Any], names: set[str], errors: list[CodecError]) -> None:
    raw = schema.get(grammar.RELATIONS_KEY)
    if raw is None:
        return
    if not isinstance(raw, list):
        errors.append(
            _err(
                grammar.RELATIONS_KEY,
                "les relations doivent former une liste.",
                "invalid_relations",
            )
        )
        return
    for i, rel in enumerate(raw):
        path = f"{grammar.RELATIONS_KEY}[{i}]"
        if not isinstance(rel, dict):
            errors.append(_err(path, "une relation doit être un objet.", "invalid_relation"))
            continue
        _check_name(rel.get("name"), f"{path}.name", errors)

        cardinality = rel.get("cardinality")
        if cardinality is None:
            errors.append(
                _err(
                    f"{path}.cardinality",
                    "`cardinality` est obligatoire.",
                    "missing_cardinality",
                    grammar.CARDINALITIES,
                )
            )
        elif cardinality not in grammar.CARDINALITIES:
            errors.append(
                _err(
                    f"{path}.cardinality",
                    f"cardinalité inconnue : « {cardinality} ».",
                    "unknown_cardinality",
                    grammar.CARDINALITIES,
                )
            )

        _check_relation_side(rel.get("from"), f"{path}.from", names, errors, local=True)
        _check_relation_side(rel.get("to"), f"{path}.to", names, errors, local=False)


def validate_schema(schema: Any) -> list[CodecError]:
    """Toutes les erreurs du schéma. Liste vide = contenu acceptable."""
    if schema is None:
        return [_err("", "le document est vide.", "empty_content")]
    if not isinstance(schema, dict):
        return [_err("", "le document doit être un objet YAML.", "invalid_root")]

    errors: list[CodecError] = []
    _check_name(schema.get("name"), "name", errors)
    names = _check_fields(schema, errors)
    _check_primary_key(schema, names, errors)
    _check_relations(schema, names, errors)
    return errors
