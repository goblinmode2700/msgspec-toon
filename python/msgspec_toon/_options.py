"""One declared option model for functional and reusable codec entry points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Domain = Literal["callable_or_none", "bool", "positive_int", "choice"]
ImplementationState = Literal["implemented", "partial"]


@dataclass(frozen=True, slots=True)
class OptionDescriptor:
    """Static behavior and forwarding metadata for one public keyword option."""

    name: str
    default: Any
    domain: Domain
    state: ImplementationState
    native_name: str | None
    functional: bool
    accepted: frozenset[Any] | None = None
    implemented: frozenset[Any] | None = None
    invalid_exception: type[Exception] = ValueError

    def validate(self, value: Any) -> None:
        if self.domain == "callable_or_none":
            if value is not None and not callable(value):
                raise TypeError(f"`{self.name}` must be callable or None")
            return
        if self.domain == "bool":
            if type(value) is not bool:
                raise TypeError(f"`{self.name}` must be a bool")
            return
        if self.domain == "positive_int":
            if type(value) is not int or value < 1:
                raise TypeError(f"`{self.name}` must be a positive integer")
            return

        accepted = self.accepted or frozenset()
        try:
            in_domain = value in accepted
        except TypeError:
            in_domain = False
        if not in_domain:
            spelled = ", ".join(sorted(repr(item) for item in accepted))
            raise self.invalid_exception(
                f"`{self.name}` must be one of {{{spelled}}}, got {value!r}"
            )
        if self.implemented is not None and value not in self.implemented:
            raise NotImplementedError(
                f"msgspec-toon does not implement `{self.name}={value!r}` yet"
            )


ENCODER_OPTIONS = (
    OptionDescriptor("enc_hook", None, "callable_or_none", "implemented", "enc_hook", True),
    OptionDescriptor(
        "decimal_format",
        "string",
        "choice",
        "implemented",
        None,
        True,
        frozenset({"string", "number"}),
    ),
    OptionDescriptor(
        "uuid_format",
        "canonical",
        "choice",
        "implemented",
        None,
        True,
        frozenset({"canonical", "hex"}),
    ),
    OptionDescriptor(
        "order",
        None,
        "choice",
        "partial",
        None,
        True,
        frozenset({None, "deterministic", "sorted"}),
        frozenset({None}),
    ),
    OptionDescriptor(
        "delimiter",
        ",",
        "choice",
        "implemented",
        "delimiter",
        True,
        frozenset({",", "\t", "|"}),
        invalid_exception=TypeError,
    ),
    OptionDescriptor("indent", 2, "positive_int", "implemented", "indent", True),
)

DECODER_OPTIONS = (
    OptionDescriptor("strict", True, "bool", "implemented", "strict", True),
    OptionDescriptor("indent_size", 2, "positive_int", "implemented", "indent_size", True),
    OptionDescriptor("dec_hook", None, "callable_or_none", "implemented", "dec_hook", True),
    OptionDescriptor("float_hook", None, "callable_or_none", "implemented", "float_hook", True),
)


def validate_python_options(
    descriptors: tuple[OptionDescriptor, ...], values: dict[str, Any]
) -> None:
    """Validate options implemented at this membrane rather than in Rust."""
    for descriptor in descriptors:
        if descriptor.native_name is None:
            descriptor.validate(values[descriptor.name])
