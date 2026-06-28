"""Moteur de filtre paramétré pour les vues sauvegardées (spec 37 — MVIEW).

Traduit une liste de prédicats JSON en fragments SQL paramétrés (AND-only).
Jamais d'interpolation de chaîne — tout passe par $n.
"""
from __future__ import annotations

from typing import Any

# ── Opérateurs valides par type de champ ─────────────────────────────────────

_SCALAR_OPS: frozenset[str] = frozenset({
    "=", "!=", "<", "<=", ">", ">=",
    "contains", "is_empty", "not_empty",
    "before", "after", "on", "between",
    "is_true", "is_false",
    "is", "is_not", "in",
})


def _validate_op(op: str) -> None:
    if op not in _SCALAR_OPS:
        raise ValueError(f"opérateur inconnu : {op!r}")


def _validate_field(field: str) -> None:
    if not field:
        raise ValueError("field vide")
    allowed_builtins = {"@type", "@bloc", "@title"}
    if field.startswith("@") and field not in allowed_builtins:
        raise ValueError(f"champ intégré inconnu : {field!r}")


# ── Génération SQL ────────────────────────────────────────────────────────────

class FilterBuilder:
    """Construit un WHERE SQL entièrement paramétré depuis une liste de prédicats."""

    def __init__(self) -> None:
        self._params: list[Any] = []
        self._clauses: list[str] = []

    def _p(self, value: Any) -> str:
        """Enregistre un paramètre et retourne son placeholder $n."""
        self._params.append(value)
        return f"${len(self._params)}"

    def add(self, predicate: dict[str, Any]) -> None:
        field: str = predicate.get("field", "")
        op: str = predicate.get("op", "")
        value = predicate.get("value")

        _validate_field(field)
        _validate_op(op)

        if field == "@type":
            self._add_builtin_type(op, value)
        elif field == "@title":
            self._add_builtin_title(op, value)
        elif field == "@bloc":
            self._add_builtin_bloc(op, value)
        else:
            self._add_property(field, op, value)

    def _add_builtin_type(self, op: str, value: Any) -> None:
        if op == "is":
            clause = (
                f"EXISTS (SELECT 1 FROM functional_type ft2 "
                f"WHERE ft2.id = d.functional_type_ref AND ft2.slug = {self._p(value)})"
            )
        elif op == "is_not":
            clause = (
                f"NOT EXISTS (SELECT 1 FROM functional_type ft2 "
                f"WHERE ft2.id = d.functional_type_ref AND ft2.slug = {self._p(value)})"
            )
        else:
            raise ValueError(f"opérateur {op!r} non supporté pour @type")
        self._clauses.append(clause)

    def _add_builtin_title(self, op: str, value: Any) -> None:
        if op == "contains":
            clause = f"d.title ILIKE '%' || {self._p(value)} || '%'"
        elif op == "is_empty":
            clause = "(d.title IS NULL OR d.title = '')"
        elif op == "not_empty":
            clause = "(d.title IS NOT NULL AND d.title <> '')"
        else:
            raise ValueError(f"opérateur {op!r} non supporté pour @title")
        self._clauses.append(clause)

    def _add_builtin_bloc(self, op: str, value: Any) -> None:
        if op == "is":
            clause = f"d.data_block_ref::text = {self._p(value)}"
        elif op == "is_not":
            clause = f"(d.data_block_ref IS NULL OR d.data_block_ref::text <> {self._p(value)})"
        else:
            raise ValueError(f"opérateur {op!r} non supporté pour @bloc")
        self._clauses.append(clause)

    def _add_property(self, prop_slug: str, op: str, value: Any) -> None:
        """EXISTS indexé sur properties_values → properties_value_version."""
        pslug = self._p(prop_slug)

        if op == "is_empty":
            # Document n'ayant pas de valeur pour cette propriété
            clause = (
                f"NOT EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug})"
            )
            self._clauses.append(clause)
            return
        if op == "not_empty":
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug})"
            )
            self._clauses.append(clause)
            return

        # Tous les autres opérateurs lisent la valeur dans properties_value_version
        version_join = (
            "JOIN properties_value_version pvv2 "
            "ON pvv2.property_value_ref = pv2.id AND pvv2.version_number = pv2.version"
        )

        if op == "is":
            # restricted_list → slug de l'allowed_value ; autres → valeur directe
            val_p = self._p(value)
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"LEFT JOIN properties_allowed_values pav2 ON pav2.id = pvv2.allowed_value_ref "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND (pvv2.value = {val_p} OR pav2.slug = {val_p}))"
            )
        elif op == "is_not":
            val_p = self._p(value)
            clause = (
                f"NOT EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"LEFT JOIN properties_allowed_values pav2 ON pav2.id = pvv2.allowed_value_ref "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND (pvv2.value = {val_p} OR pav2.slug = {val_p}))"
            )
        elif op == "contains":
            val_p = self._p(value)
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value ILIKE '%' || {val_p} || '%')"
            )
        elif op in {"=", "!=", "<", "<=", ">", ">="}:
            val_p = self._p(str(value))
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value {op} {val_p})"
            )
        elif op == "before":
            val_p = self._p(str(value))
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value < {val_p})"
            )
        elif op == "after":
            val_p = self._p(str(value))
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value > {val_p})"
            )
        elif op == "on":
            val_p = self._p(str(value))
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value = {val_p})"
            )
        elif op == "between":
            lo = self._p(str(value[0]) if isinstance(value, list) and len(value) > 0 else "")
            hi = self._p(str(value[1]) if isinstance(value, list) and len(value) > 1 else "")
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value BETWEEN {lo} AND {hi})"
            )
        elif op == "is_true":
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value = 'true')"
            )
        elif op == "is_false":
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND pvv2.value = 'false')"
            )
        elif op == "in":
            if not isinstance(value, list) or not value:
                raise ValueError("opérateur 'in' nécessite une liste non vide")
            placeholders = ", ".join(self._p(v) for v in value)
            clause = (
                f"EXISTS ("
                f"SELECT 1 FROM properties_values pv2 "
                f"JOIN properties_defs pd2 ON pd2.id = pv2.property_def_ref "
                f"{version_join} "
                f"LEFT JOIN properties_allowed_values pav2 ON pav2.id = pvv2.allowed_value_ref "
                f"WHERE pv2.document_ref = d.doc_technical_key AND pd2.slug = {pslug} "
                f"AND (pvv2.value IN ({placeholders}) OR pav2.slug IN ({placeholders})))"
            )
        else:
            raise ValueError(f"opérateur non implémenté : {op!r}")

        self._clauses.append(clause)

    def where_clause(self) -> str:
        """Retourne les fragments AND à insérer dans la requête principale."""
        if not self._clauses:
            return ""
        return " AND " + " AND ".join(self._clauses)

    @property
    def params(self) -> list[Any]:
        return list(self._params)
