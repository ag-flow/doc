"""Codec du type de contenu `table-schema` (épic MLD — F5).

Un document décrit **une table** : ses champs et ses relations vers d'autres
tables. Grammaire : Table Schema (Frictionless) + extensions sous `docflow.`
(cf. `grammar`). C'est le contenu que F7 rendra sur le canvas.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from docflow.codecs.base import CodecError, ContentCodec, DocumentReferences
from docflow.codecs.table_schema import grammar, ids, yaml_io
from docflow.codecs.table_schema.validate import validate_schema

CONTENT_TYPE = "table-schema"

#: Référence vers un autre document, écrite littéralement dans une description.
_DOC_REF = re.compile(r"docflow://doc/([0-9a-fA-F-]{36})")


class TableSchemaCodec(ContentCodec[dict[str, Any]]):
    """Codec `table-schema`. Le modèle canonique est le schéma désérialisé."""

    content_type = CONTENT_TYPE

    # ── Lecture (fail-soft) ───────────────────────────────────────────────────

    def parse(self, content: str | None) -> dict[str, Any]:
        """Contenu → schéma. Ne lève jamais : un document abîmé reste lisible.

        Le refus d'un contenu mal formé est le rôle de `validate`, sur le chemin
        d'écriture. Ici, un YAML cassé rend un schéma vide plutôt que de casser
        l'affichage ou la sauvegarde.
        """
        try:
            loaded = yaml_io.load(content)
        except yaml_io.YamlSyntaxError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def serialize(self, model: dict[str, Any]) -> str:
        """Schéma → YAML canonique (ordre de clés figé, identifiants alloués)."""
        return yaml_io.dump(self._canonicalize(dict(model))) if model else ""

    def to_plain_text(self, content: str | None) -> str:
        """Projection pour la recherche et le RAG.

        Rend le SENS du modèle — libellés et descriptions d'abord, puisque c'est
        là qu'un humain écrit ce que la donnée veut dire — et jamais la syntaxe
        YAML. Sans quoi chercher « type » ou « name » remonterait toutes les
        tables, ces mots étant des mots-clés de la grammaire.
        """
        schema = self.parse(content)
        if not schema:
            # Contenu illisible : on renvoie le brut plutôt que rien, sinon le
            # document deviendrait introuvable.
            return (content or "").strip()

        parts: list[str] = []
        for key in ("name", "title", "description"):
            value = schema.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

        for entry_key in ("fields", grammar.RELATIONS_KEY):
            entries = schema.get(entry_key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for key in ("name", "title", "description"):
                    value = entry.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
        return "\n".join(parts)

    def references(self, content: str | None) -> DocumentReferences:
        """Références `docflow://doc/<uuid>` écrites dans les textes libres.

        Ni artefact ni dataset : cette grammaire n'en porte pas. Ne rien
        extraire pour ces familles est exact, pas un oubli — et c'est sans
        danger puisque le codec déclare savoir lire (`extracts_references`).
        """
        documents: dict[str, str] = {}
        for raw in _DOC_REF.findall(content or ""):
            try:
                documents[str(uuid.UUID(raw))] = ""
            except ValueError:
                continue
        return DocumentReferences(documents=documents)

    # ── Écriture ──────────────────────────────────────────────────────────────

    def validate(self, content: str | None) -> list[CodecError]:
        """Toutes les erreurs empêchant d'accepter ce contenu."""
        try:
            loaded = yaml_io.load(content)
        except yaml_io.YamlSyntaxError as exc:
            return [
                CodecError(
                    path="",
                    message=f"YAML illisible : {exc.detail}",
                    code="content_unparseable",
                    doc=grammar.GRAMMAR_DOC,
                )
            ]
        return validate_schema(loaded)

    def canonicalize(self, content: str | None) -> str:
        """Contenu → forme canonique, identifiants stables alloués.

        Appelé côté SERVEUR avant enregistrement : c'est ce qui garantit qu'un
        même modèle s'écrit toujours pareil, quel que soit l'auteur ou l'outil.

        **Ne détruit jamais** : un contenu illisible est rendu TEL QUEL. La
        canonicalisation est sur le chemin de sauvegarde, où l'on n'a pas le
        droit de perdre le travail de l'utilisateur — le refus d'un contenu
        invalide est le rôle de `validate`, à la frontière de l'API.
        """
        schema = self.parse(content)
        if not schema:
            return content or ""
        return yaml_io.dump(self._canonicalize(schema))

    # ── Interne ───────────────────────────────────────────────────────────────

    def _canonicalize(self, schema: dict[str, Any]) -> dict[str, Any]:
        taken = ids.collect_existing(schema, grammar.ID_KEY)
        schema["fields"] = self._canonical_entries(
            schema.get("fields"), ids.FIELD_PREFIX, grammar.FIELD_KEY_ORDER, taken
        )
        if grammar.RELATIONS_KEY in schema:
            schema[grammar.RELATIONS_KEY] = self._canonical_entries(
                schema.get(grammar.RELATIONS_KEY),
                ids.RELATION_PREFIX,
                grammar.RELATION_KEY_ORDER,
                taken,
            )
        return grammar.order_keys(schema, grammar.SCHEMA_KEY_ORDER)

    @staticmethod
    def _canonical_entries(
        entries: Any, prefix: str, order: tuple[str, ...], taken: set[str]
    ) -> list[Any]:
        """Alloue les identifiants manquants et réordonne chaque entrée."""
        if not isinstance(entries, list):
            return []
        result: list[Any] = []
        for entry in entries:
            if not isinstance(entry, dict):
                result.append(entry)
                continue
            if not ids.is_valid(entry.get(grammar.ID_KEY)):
                entry[grammar.ID_KEY] = ids.new_id(prefix, taken)
            constraints = entry.get("constraints")
            if isinstance(constraints, dict):
                entry["constraints"] = grammar.order_keys(constraints, grammar.CONSTRAINT_KEY_ORDER)
            result.append(grammar.order_keys(entry, order))
        return result
