"""The normalized type-plan IR passed from the plan compiler into Rust.

This is the only schema the native module understands. `msgspec.inspect` never
crosses this boundary (canvas AD-003).
"""

from __future__ import annotations

from dataclasses import dataclass
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
    "native_scalar",
    "custom",
]

_UNSET = object()


@dataclass(frozen=True, slots=True)
class FieldSpec:
    python_name: str
    wire_name: str
    plan: int
    required: bool
    default: Any = _UNSET
    default_factory: Any = None


@dataclass(frozen=True, slots=True)
class PlanSpec:
    kind: PlanKind
    python_type: Any = None
    item: int | None = None
    key: int | None = None
    value: int | None = None
    items: tuple[Any, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    tag_field: str | None = None
    tag_value: Any = None
    array_like: bool = False
    forbid_unknown_fields: bool = False
    #: The class must be constructed with keyword arguments (`kw_only=True`,
    #: or any keyword-only field). msgspec exposes this on neither
    #: `StructConfig` nor `msgspec.inspect`, so the plan compiler reads the
    #: constructor signature and records the answer here.
    keyword_only: bool = False
    constraints: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class PlanGraph:
    """An indexed, immutable annotation graph.

    Child edges are node indexes. This permits recursive annotations without
    creating recursive Python owners and gives the native compiler one bounded
    arena to validate before decoding starts.
    """

    nodes: tuple[PlanSpec, ...]
    root: int

    @property
    def root_spec(self) -> PlanSpec:
        return self.nodes[self.root]
