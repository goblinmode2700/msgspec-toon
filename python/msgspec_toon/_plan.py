"""Compile msgspec type annotations into the normalized PlanSpec IR.

This module is the compatibility membrane (canvas AD-003): it is the ONLY
module in the package allowed to import `msgspec.inspect`. Everything past
this point — including all Rust code — sees only PlanSpec/FieldSpec.
"""

from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Any

import msgspec
import msgspec.inspect as mi

from ._types import _UNSET, FieldSpec, PlanSpec

_NODEFAULT = msgspec.NODEFAULT


@lru_cache(maxsize=512)
def compile_plan(annotation: Any) -> PlanSpec:
    return _lower(mi.type_info(annotation))


def _is_keyword_only(cls: type) -> bool:
    """Whether the Struct must be constructed with keyword arguments.

    `kw_only=True` reorders `__struct_fields__` so required fields come first,
    and the generated constructor takes keyword-only parameters — a positional
    vectorcall then fails with "Extra positional arguments provided" (review
    F-09). msgspec publishes the flag on neither `StructConfig` nor
    `msgspec.inspect`, so the constructor signature is the source of truth. Any
    keyword-only parameter is enough: passing every argument by keyword is
    valid for ordinary parameters too, so one branch covers partial cases.
    """
    return any(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in inspect.signature(cls).parameters.values()
    )


def _lower_mapping_key(info: mi.Type) -> PlanSpec:
    """Only `str` keys decode correctly, so only `str` keys compile.

    The typed consumer builds every mapping key as a Python string, and the key
    plan reached Rust but was never applied: `dict[int, int]` decoded to
    `{"1": 2}` while `msgspec.json` returns `{1: 2}` (review F-13). A wrong
    value returned silently is worse than a refusal, and the earliest place to
    refuse is where the annotation is first seen — so this raises when the
    Decoder is constructed, not when a document happens to contain a key.
    """
    match info:
        case mi.StrType():
            return _lower(info)
        case _:
            raise TypeError(
                "msgspec-toon supports only str-keyed mappings; "
                f"{type(info).__name__} keys are not implemented"
            )


def _lower(info: mi.Type) -> PlanSpec:
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
        case mi.ListType(item_type=item):
            return PlanSpec("list", python_type=list, item=_lower(item))
        case mi.VarTupleType(item_type=item):
            return PlanSpec("tuple_var", python_type=tuple, item=_lower(item))
        case mi.TupleType(item_types=items):
            return PlanSpec("tuple_fixed", python_type=tuple, items=tuple(map(_lower, items)))
        case mi.DictType(key_type=key, value_type=value):
            return PlanSpec(
                "dict", python_type=dict, key=_lower_mapping_key(key), value=_lower(value)
            )
        case mi.UnionType(types=items):
            return PlanSpec("union", items=tuple(map(_lower, items)))
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
                        plan=_lower(item.type),
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
    return tuple(
        (name, value) for name in names if (value := getattr(info, name, None)) is not None
    )


def encode_plan_for(cls: type) -> PlanSpec:
    """Compile the encode-side plan for a Struct class encountered at runtime."""
    if not (isinstance(cls, type) and issubclass(cls, msgspec.Struct)):
        raise TypeError(f"encode_plan_for expects a Struct class, got {cls!r}")
    return compile_plan(cls)
