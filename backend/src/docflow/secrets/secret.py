from __future__ import annotations

from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


class Secret:
    """Wraps a string that must never appear in logs or reprs.

    Call .reveal() only at the point of injection (HTTP call, DB write, etc.).
    ${vault://apiname:/path} references are resolved by secrets.resolver.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def __repr__(self) -> str:
        return "Secret(***)"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return self._value == other._value
        return NotImplemented

    def reveal(self) -> str:
        """Return the raw value. Call only at the point of injection."""
        return self._value

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            lambda v: v if isinstance(v, cls) else cls(str(v)),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda _: "***",
                info_arg=False,
            ),
        )
