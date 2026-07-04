"""Tests unitaires (sans DB) du rendu SQL de FilterBuilder — DOC-01.

Vérifie que les placeholders $n sont émis contigus et correctement mappés,
y compris avec un offset et pour les opérateurs à occurrences multiples
(is / is_not / in) qui réutilisent le même placeholder plusieurs fois.
"""

from __future__ import annotations

import re

import pytest

from docflow.views.filter_engine import FilterBuilder


def _numbers(sql: str) -> list[int]:
    """Extrait tous les numéros de placeholders $n dans l'ordre d'apparition."""
    return [int(m) for m in re.findall(r"\$(\d+)\b", sql)]


def test_is_operator_offset_duplicated_placeholder() -> None:
    """`is` sur propriété réutilise le placeholder valeur 2 fois — les deux
    occurrences doivent porter le même numéro, décalé de l'offset."""
    fb = FilterBuilder(offset=2)
    fb.add({"field": "status", "op": "is", "value": "open"})

    sql = fb.where_clause()
    assert fb.params == ["status", "open"]
    # $3 = slug de la propriété, $4 = valeur (deux occurrences : pvv2.value / pav2.slug)
    nums = _numbers(sql)
    assert nums == [3, 4, 4]
    assert "pd2.slug = $3" in sql
    assert "(pvv2.value = $4 OR pav2.slug = $4)" in sql
    # Aucun placeholder résiduel non décalé ($1/$2 réservés à l'appelant)
    assert 1 not in nums and 2 not in nums


def test_three_contains_predicates_are_contiguous_and_ordered() -> None:
    """3 prédicats `contains` → 6 params, placeholders $3..$8 contigus,
    chaque clause pointant sur la bonne paire (slug, valeur)."""
    fb = FilterBuilder(offset=2)
    fb.add({"field": "alpha", "op": "contains", "value": "a"})
    fb.add({"field": "beta", "op": "contains", "value": "b"})
    fb.add({"field": "gamma", "op": "contains", "value": "c"})

    sql = fb.where_clause()
    assert fb.params == ["alpha", "a", "beta", "b", "gamma", "c"]
    assert _numbers(sql) == [3, 4, 5, 6, 7, 8]  # contigus, ordre d'émission
    # Chaque valeur est associée au slug de son propre prédicat (pas de permutation)
    assert "pd2.slug = $3 AND pvv2.value ILIKE '%' || $4 || '%'" in sql
    assert "pd2.slug = $5 AND pvv2.value ILIKE '%' || $6 || '%'" in sql
    assert "pd2.slug = $7 AND pvv2.value ILIKE '%' || $8 || '%'" in sql


def test_in_operator_repeats_each_placeholder_twice() -> None:
    """`in` émet chaque placeholder de la liste dans deux IN (...) distincts."""
    fb = FilterBuilder(offset=2)
    fb.add({"field": "status", "op": "in", "value": ["open", "closed"]})

    sql = fb.where_clause()
    assert fb.params == ["status", "open", "closed"]
    assert "(pvv2.value IN ($4, $5) OR pav2.slug IN ($4, $5))" in sql
    assert _numbers(sql) == [3, 4, 5, 4, 5]


def test_large_number_of_params_no_prefix_collision() -> None:
    """Au-delà de 9 params, $1x ne doit jamais être corrompu (ancien bug
    de renumérotation où $1 matchait le préfixe de $10)."""
    fb = FilterBuilder(offset=2)
    for i in range(6):  # 6 prédicats × 2 params = 12 params → $3..$14
        fb.add({"field": f"prop{i}", "op": "contains", "value": f"v{i}"})

    sql = fb.where_clause()
    assert len(fb.params) == 12
    assert _numbers(sql) == list(range(3, 15))


def test_offset_zero_default_starts_at_one() -> None:
    fb = FilterBuilder()
    fb.add({"field": "@title", "op": "contains", "value": "x"})
    assert fb.params == ["x"]
    assert _numbers(fb.where_clause()) == [1]


def test_negative_offset_rejected() -> None:
    with pytest.raises(ValueError):
        FilterBuilder(offset=-1)


def test_builtin_type_is_with_offset() -> None:
    fb = FilterBuilder(offset=2)
    fb.add({"field": "@type", "op": "is", "value": "epic"})
    assert fb.params == ["epic"]
    assert "ft2.slug = $3" in fb.where_clause()


def test_mixed_predicates_contiguous_after_duplicates() -> None:
    """Un `is` (placeholder dupliqué) suivi d'un `contains` : le prédicat
    suivant continue la séquence sans trou ni collision."""
    fb = FilterBuilder(offset=2)
    fb.add({"field": "status", "op": "is", "value": "open"})
    fb.add({"field": "title-prop", "op": "contains", "value": "urgent"})

    sql = fb.where_clause()
    assert fb.params == ["status", "open", "title-prop", "urgent"]
    assert _numbers(sql) == [3, 4, 4, 5, 6]
    assert "pd2.slug = $5 AND pvv2.value ILIKE '%' || $6 || '%'" in sql
