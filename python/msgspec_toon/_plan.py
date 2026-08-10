"""Compile msgspec type annotations into the normalized PlanSpec IR.

This module is the compatibility membrane (canvas AD-003): it is the ONLY
module in the package allowed to import `msgspec.inspect`. Everything past
this point — including all Rust code — sees only PlanSpec/FieldSpec.
"""

from __future__ import annotations

import datetime
import decimal
import inspect
import re
import uuid
from functools import lru_cache
from typing import Annotated, Any

import msgspec
import msgspec.inspect as mi

from . import _native  # type: ignore[attr-defined]
from ._exceptions import TypePlanError
from ._types import _UNSET, FieldSpec, PlanGraph, PlanSpec

_NODEFAULT = msgspec.NODEFAULT


@lru_cache(maxsize=512)
def compile_plan(annotation: Any, allow_custom: bool = False) -> PlanGraph:
    """Lower one annotation, containing all inspection failures at this membrane."""
    try:
        info = mi.type_info(annotation)
    except Exception:  # noqa: BLE001 - the public membrane contains inspect internals
        raise TypePlanError(code="unsupported_annotation", path=()) from None
    try:
        compiler = _GraphCompiler(allow_custom=allow_custom)
        root = compiler.lower(info, path=(), depth=0)
        return PlanGraph(tuple(compiler.complete()), root)
    except TypePlanError:
        raise
    except Exception:  # noqa: BLE001 - no lowering implementation error may leak
        raise TypePlanError(code="invalid_plan", path=()) from None


@lru_cache(maxsize=512)
def compile_native_plan(annotation: Any, allow_custom: bool = False) -> _native.NativePlan:
    """Compile and retain the opaque native plan at the inspection membrane."""
    try:
        return _native.compile_plan(compile_plan(annotation, allow_custom=allow_custom))
    except TypePlanError:
        raise
    except Exception:  # noqa: BLE001 - native plan faults are package-contained
        raise TypePlanError(code="invalid_native_plan", path=()) from None


def _is_keyword_only(cls: type) -> bool:
    """Whether the Struct must be constructed with keyword arguments.

    `kw_only=True` reorders `__struct_fields__` so required fields come first,
    and the generated constructor takes keyword-only parameters — a positional
    vectorcall then fails with "Extra positional arguments provided" (review
    keyword-only construction). msgspec publishes the flag on neither `StructConfig` nor
    `msgspec.inspect`, so the constructor signature is the source of truth. Any
    keyword-only parameter is enough: passing every argument by keyword is
    valid for ordinary parameters too, so one branch covers partial cases.
    """
    return any(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in inspect.signature(cls).parameters.values()
    )


def _lower_mapping_key(
    info: mi.Type,
    *,
    path: tuple[str, ...],
    compiler: _GraphCompiler,
    depth: int,
) -> int:
    """Only `str` keys decode correctly, so only `str` keys compile.

    The typed consumer builds every mapping key as a Python string, and the key
    plan reached Rust but was never applied: `dict[int, int]` decoded to
    `{"1": 2}` while `msgspec.json` returns `{1: 2}`. A wrong
    value returned silently is worse than a refusal, and the earliest place to
    refuse is where the annotation is first seen — so this raises when the
    Decoder is constructed, not when a document happens to contain a key.
    """
    match info:
        case mi.StrType():
            return compiler.lower(info, path=path, depth=depth)
        case _:
            raise TypePlanError(code="unsupported_mapping_key", path=path)


class _GraphCompiler:
    """Compile inspected annotations once, with explicit graph states."""

    __slots__ = ("allow_custom", "by_identity", "kinds", "nodes", "states")

    _MAX_NODES = 4096
    _MAX_STATIC_DEPTH = 128

    def __init__(self, *, allow_custom: bool) -> None:
        self.allow_custom = allow_custom
        self.nodes: list[PlanSpec | None] = []
        self.states: list[str] = []
        self.by_identity: dict[int, int] = {}
        self.kinds: list[str] = []

    def complete(self) -> list[PlanSpec]:
        if any(node is None for node in self.nodes):
            raise TypePlanError(code="invalid_plan", path=())
        return [node for node in self.nodes if node is not None]

    def lower(self, info: mi.Type, *, path: tuple[str, ...], depth: int) -> int:
        if depth > self._MAX_STATIC_DEPTH:
            raise TypePlanError(code="annotation_depth", path=path)
        identity = id(info)
        if identity in self.by_identity:
            index = self.by_identity[identity]
            if self.states[index] == "visiting" and self.kinds[index] != "struct":
                raise TypePlanError(code="unsupported_cycle", path=path)
            return index
        if len(self.nodes) >= self._MAX_NODES:
            raise TypePlanError(code="annotation_size", path=path)
        index = len(self.nodes)
        self.by_identity[identity] = index
        self.nodes.append(None)
        self.states.append("visiting")
        self.kinds.append("struct" if isinstance(info, mi.StructType) else "other")
        try:
            node = self._lower_new(info, path=path, depth=depth)
        except Exception:
            self.states[index] = "failed"
            raise
        self.nodes[index] = node
        self.states[index] = "complete"
        return index

    def _child(self, info: mi.Type, path: tuple[str, ...], depth: int) -> int:
        return self.lower(info, path=path, depth=depth + 1)

    def _lower_new(self, info: mi.Type, *, path: tuple[str, ...], depth: int) -> PlanSpec:
        match info:
            case mi.AnyType():
                return PlanSpec("any")
            case mi.NoneType():
                return PlanSpec("none")
            case mi.BoolType():
                return PlanSpec("bool")
            case mi.IntType():
                return PlanSpec("int", constraints=_constraints(info))
            case mi.FloatType():
                return PlanSpec("float", constraints=_constraints(info))
            case mi.StrType():
                return PlanSpec("str", constraints=_constraints(info))
            case mi.DateTimeType(tz=tz):
                datetime_target = (
                    datetime.datetime
                    if tz is None
                    else Annotated[datetime.datetime, msgspec.Meta(tz=tz)]
                )
                return PlanSpec(
                    "native_scalar", python_type=datetime_target, constraints=_constraints(info)
                )
            case mi.DateType():
                return PlanSpec("native_scalar", python_type=datetime.date)
            case mi.TimeType(tz=tz):
                time_target = (
                    datetime.time if tz is None else Annotated[datetime.time, msgspec.Meta(tz=tz)]
                )
                return PlanSpec(
                    "native_scalar", python_type=time_target, constraints=_constraints(info)
                )
            case mi.TimeDeltaType():
                return PlanSpec("native_scalar", python_type=datetime.timedelta)
            case mi.UUIDType():
                return PlanSpec("native_scalar", python_type=uuid.UUID)
            case mi.DecimalType():
                return PlanSpec("native_scalar", python_type=decimal.Decimal)
            case mi.EnumType(cls=cls):
                return PlanSpec("native_scalar", python_type=cls)
            case mi.ListType(item_type=item):
                return PlanSpec(
                    "list",
                    python_type=list,
                    item=self._child(item, (*path, "[]"), depth),
                    constraints=_constraints(info),
                )
            case mi.VarTupleType(item_type=item):
                return PlanSpec(
                    "tuple_var",
                    python_type=tuple,
                    item=self._child(item, (*path, "[]"), depth),
                    constraints=_constraints(info),
                )
            case mi.TupleType(item_types=items):
                return PlanSpec(
                    "tuple_fixed",
                    python_type=tuple,
                    items=tuple(
                        self._child(item, (*path, f"[{index}]"), depth)
                        for index, item in enumerate(items)
                    ),
                )
            case mi.DictType(key_type=key, value_type=value):
                return PlanSpec(
                    "dict",
                    python_type=dict,
                    key=_lower_mapping_key(
                        key,
                        path=(*path, "[key]"),
                        compiler=self,
                        depth=depth + 1,
                    ),
                    value=self._child(value, (*path, "[value]"), depth),
                    constraints=_constraints(info),
                )
            case mi.UnionType(types=items):
                non_none = [item for item in items if not isinstance(item, mi.NoneType)]
                if len(non_none) > 1:
                    tagged = [item for item in non_none if isinstance(item, mi.StructType)]
                    tag_fields = {item.tag_field for item in tagged}
                    tag_values = [item.tag for item in tagged]
                    array_shapes = {item.array_like for item in tagged}
                    if (
                        len(tagged) != len(non_none)
                        or len(array_shapes) != 1
                        or None in tag_fields
                        or len(tag_fields) != 1
                        or len({(type(value), value) for value in tag_values}) != len(tag_values)
                    ):
                        raise TypePlanError(code="unsupported_union", path=path)
                return PlanSpec(
                    "union",
                    items=tuple(
                        self._child(item, (*path, f"[union:{index}]"), depth)
                        for index, item in enumerate(items)
                    ),
                )
            case mi.LiteralType(values=values):
                return PlanSpec("literal", items=tuple(values))
            case mi.StructType(
                cls=cls,
                fields=fields,
                tag_field=tag_field,
                tag=tag,
                array_like=array_like,
                forbid_unknown_fields=forbid_unknown_fields,
            ):
                return PlanSpec(
                    "struct",
                    python_type=cls,
                    fields=tuple(
                        FieldSpec(
                            python_name=item.name,
                            wire_name=item.encode_name,
                            plan=self._child(item.type, (*path, item.name), depth),
                            required=item.required,
                            default=_UNSET if item.default is _NODEFAULT else item.default,
                            default_factory=(
                                None if item.default_factory is _NODEFAULT else item.default_factory
                            ),
                        )
                        for item in fields
                    ),
                    tag_field=tag_field,
                    tag_value=tag,
                    array_like=array_like,
                    forbid_unknown_fields=forbid_unknown_fields,
                    keyword_only=_is_keyword_only(cls),
                )
            case _:
                if not self.allow_custom:
                    raise TypePlanError(code="unsupported_custom_type", path=path)
                return PlanSpec("custom", python_type=getattr(info, "cls", None))


def _constraints(info: Any) -> tuple[tuple[str, Any], ...]:
    names = (
        "ge",
        "gt",
        "le",
        "lt",
        "multiple_of",
        "min_length",
        "max_length",
        "pattern",
        "tz",
    )
    constraints: list[tuple[str, Any]] = []
    for name in names:
        value = getattr(info, name, None)
        if value is None:
            continue
        # msgspec uses Python regex search semantics. Compile once at the
        # inspection membrane so Rust receives an executable schema object,
        # not a second regex implementation with subtly different behavior.
        if name == "pattern":
            value = re.compile(value)
        constraints.append((name, value))
    return tuple(constraints)


def encode_plan_for(cls: type) -> PlanGraph:
    """Compile the encode-side plan for a Struct class encountered at runtime."""
    if not (isinstance(cls, type) and issubclass(cls, msgspec.Struct)):
        raise TypeError(f"encode_plan_for expects a Struct class, got {cls!r}")
    return compile_plan(cls, allow_custom=True)
