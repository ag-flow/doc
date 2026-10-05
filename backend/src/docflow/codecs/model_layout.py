"""Codec du type de contenu `model-layout` (épic MLD — F7).

Un document `model-layout` est le **document contexte** d'un modèle de données :
il porte la mise en page du diagramme, et rien d'autre. Les entités elles-mêmes
sont ses **documents enfants**, de type `table-schema`.

Séparation structurante, exigée par le cadrage :

- **Sémantique** — ce que le modèle décrit — vit dans les enfants `table-schema` ;
- **Présentation** — où les boîtes sont posées — vit ici.

**La vérité d'appartenance au modèle est l'ARBORESCENCE** (`document.parent`),
jamais ce fichier. Deux conséquences tenues par le code appelant :

- une entité absente du layout est placée automatiquement — elle appartient
  quand même au modèle ;
- une entrée de layout qui ne correspond à aucun enfant est **ignorée** — un
  reliquat de présentation ne ressuscite pas une entité supprimée.

Conséquence sur la recherche : la projection texte est **vide**. Des coordonnées
ne veulent rien dire pour un humain qui cherche ; le sens du modèle est dans les
entités, qui sont indexées chacune de leur côté.
"""

from __future__ import annotations

from typing import Any

from docflow.codecs.base import CodecError, ContentCodec
from docflow.codecs.table_schema import yaml_io

CONTENT_TYPE = "model-layout"

#: Article de grammaire (bloc Documentation).
GRAMMAR_DOC = "docflow://doc/e29576c2-eaf7-4cc4-844c-b5db356f9dc7"

SCHEMA_VERSION = 1

_ENTITY_KEY_ORDER = ("id", "x", "y", "width", "height", "collapsed")
_RELATION_KEY_ORDER = ("id", "waypoints")
_ROOT_KEY_ORDER = ("schemaVersion", "viewport", "entities", "relations")


def _err(path: str, message: str, code: str) -> CodecError:
    return CodecError(path=path, message=message, code=code, doc=GRAMMAR_DOC)


def _check_number(value: Any, path: str, errors: list[CodecError]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(_err(path, "une coordonnée doit être un nombre.", "invalid_number"))


class ModelLayoutCodec(ContentCodec[dict[str, Any]]):
    """Codec `model-layout`. Le modèle canonique est la mise en page désérialisée."""

    content_type = CONTENT_TYPE

    # ── Lecture (fail-soft) ───────────────────────────────────────────────────

    def parse(self, content: str | None) -> dict[str, Any]:
        try:
            loaded = yaml_io.load(content)
        except yaml_io.YamlSyntaxError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def serialize(self, model: dict[str, Any]) -> str:
        return yaml_io.dump(self._canonical(dict(model))) if model else ""

    def to_plain_text(self, content: str | None) -> str:
        """Vide, à dessein.

        Une mise en page n'a aucun contenu cherchable : personne ne retrouve un
        modèle en tapant des coordonnées. Le sens est dans les entités enfants,
        indexées chacune par son propre codec — le remonter ici le dupliquerait
        et polluerait les résultats de recherche.
        """
        return ""

    # ── Écriture ──────────────────────────────────────────────────────────────

    def validate(self, content: str | None) -> list[CodecError]:
        if content is None or not content.strip():
            # Un modèle qui vient de naître n'a pas encore de mise en page :
            # c'est un état normal, pas une erreur.
            return []
        try:
            loaded = yaml_io.load(content)
        except yaml_io.YamlSyntaxError as exc:
            return [
                CodecError(
                    path="",
                    message=f"YAML illisible : {exc.detail}",
                    code="content_unparseable",
                    doc=GRAMMAR_DOC,
                )
            ]
        return self._validate_layout(loaded)

    def canonicalize(self, content: str | None) -> str:
        layout = self.parse(content)
        if not layout:
            return content or ""
        return yaml_io.dump(self._canonical(layout))

    # ── Interne ───────────────────────────────────────────────────────────────

    def _validate_layout(self, layout: Any) -> list[CodecError]:
        if layout is None:
            return []
        if not isinstance(layout, dict):
            return [_err("", "la mise en page doit être un objet YAML.", "invalid_root")]

        errors: list[CodecError] = []
        entities = layout.get("entities")
        if entities is not None:
            if not isinstance(entities, list):
                errors.append(
                    _err("entities", "`entities` doit être une liste.", "invalid_entities")
                )
            else:
                seen: set[str] = set()
                for i, entity in enumerate(entities):
                    path = f"entities[{i}]"
                    if not isinstance(entity, dict):
                        errors.append(
                            _err(path, "une entrée doit être un objet.", "invalid_entity")
                        )
                        continue
                    ref = entity.get("id")
                    if not isinstance(ref, str) or not ref:
                        errors.append(_err(f"{path}.id", "`id` est obligatoire.", "missing_id"))
                    elif ref in seen:
                        errors.append(
                            _err(f"{path}.id", f"entrée dupliquée : « {ref} ».", "duplicate_id")
                        )
                    else:
                        seen.add(ref)
                    for axis in ("x", "y"):
                        if axis in entity:
                            _check_number(entity[axis], f"{path}.{axis}", errors)

        relations = layout.get("relations")
        if relations is not None and not isinstance(relations, list):
            errors.append(
                _err("relations", "`relations` doit être une liste.", "invalid_relations")
            )
        elif isinstance(relations, list):
            for i, rel in enumerate(relations):
                path = f"relations[{i}]"
                if not isinstance(rel, dict):
                    errors.append(_err(path, "une entrée doit être un objet.", "invalid_relation"))
                    continue
                if not isinstance(rel.get("id"), str):
                    errors.append(_err(f"{path}.id", "`id` est obligatoire.", "missing_id"))
                waypoints = rel.get("waypoints")
                if waypoints is not None and not isinstance(waypoints, list):
                    errors.append(
                        _err(
                            f"{path}.waypoints",
                            "`waypoints` doit être une liste.",
                            "invalid_waypoints",
                        )
                    )
        return errors

    def _canonical(self, layout: dict[str, Any]) -> dict[str, Any]:
        layout.setdefault("schemaVersion", SCHEMA_VERSION)
        for key, order in (("entities", _ENTITY_KEY_ORDER), ("relations", _RELATION_KEY_ORDER)):
            entries = layout.get(key)
            if isinstance(entries, list):
                layout[key] = [_order(e, order) if isinstance(e, dict) else e for e in entries]
        return _order(layout, _ROOT_KEY_ORDER)


def _order(mapping: dict[str, Any], order: tuple[str, ...]) -> dict[str, Any]:
    """Réordonne ; les clés inconnues suivent, triées — et ne sont jamais jetées."""
    ordered = {k: mapping[k] for k in order if k in mapping}
    rest = {k: mapping[k] for k in sorted(mapping) if k not in ordered}
    return {**ordered, **rest}
