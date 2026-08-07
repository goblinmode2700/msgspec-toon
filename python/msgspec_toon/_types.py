"""The normalized type-plan IR passed from the plan compiler into Rust.

This is the only schema the native module understands. `msgspec.inspect` never
crosses this boundary (canvas AD-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PlanKind = Literal[
    "any",
    "none",
    "bool",
    "int",
    "float",
    "str",
    "list",
    "tuple_var",
    "tuple_fixed",
    "dict",
    "struct",
    "union",
    "literal",
    "custom",
]

_UNSET = object()


@dataclass(frozen=True, slots=True)
class FieldSpec:
    python_name: str
    wire_name: str
    plan: PlanSpec
    required: bool
    default: Any = _UNSET
    default_factory: Any = None


@dataclass(frozen=True, slots=True)
class PlanSpec:
    kind: PlanKind
    python_type: Any = None
    item: PlanSpec | None = None
    key: PlanSpec | None = None
    value: PlanSpec | None = None
    items: tuple[Any, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    tag_field: str | None = None
    tag_value: Any = None
    array_like: bool = False
    forbid_unknown_fields: bool = False
    constraints: tuple[tuple[str, Any], ...] = ()
