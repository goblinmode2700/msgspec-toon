"""The descriptor model polices functional and reusable option behavior."""

from __future__ import annotations

import inspect

import msgspec_toon as toon
import pytest
from msgspec_toon import _native
from msgspec_toon._options import DECODER_OPTIONS, ENCODER_OPTIONS


@pytest.mark.parametrize(
    ("descriptors", "reusable", "functional"),
    [
        (ENCODER_OPTIONS, toon.Encoder, toon.encode),
        (DECODER_OPTIONS, toon.Decoder, toon.decode),
    ],
)
def test_explicit_signatures_match_option_descriptors(
    descriptors: tuple[object, ...], reusable: object, functional: object
) -> None:
    reusable_parameters = inspect.signature(reusable).parameters
    functional_parameters = inspect.signature(functional).parameters
    for descriptor in descriptors:
        name = descriptor.name
        assert reusable_parameters[name].default == descriptor.default
        if descriptor.functional:
            assert functional_parameters[name].default == descriptor.default
        else:
            assert name not in functional_parameters


@pytest.mark.parametrize("descriptors", [ENCODER_OPTIONS, DECODER_OPTIONS])
def test_every_descriptor_declares_forwarding_and_state(descriptors: tuple[object, ...]) -> None:
    for descriptor in descriptors:
        assert descriptor.state in {"implemented", "partial"}
        assert descriptor.native_name is None or isinstance(descriptor.native_name, str)
        assert descriptor.functional in {True, False}


@pytest.mark.parametrize(
    ("descriptors", "construct"),
    [
        (ENCODER_OPTIONS, lambda: toon.Encoder()),
        (DECODER_OPTIONS, lambda: toon.Decoder()),
    ],
)
def test_native_forwarding_is_derived_from_descriptors(
    monkeypatch: pytest.MonkeyPatch, descriptors: tuple[object, ...], construct: object
) -> None:
    forwarded: dict[str, object] = {}

    def capture(**kwargs: object) -> object:
        forwarded.update(kwargs)
        return object()

    native_class = _native.Encoder if descriptors is ENCODER_OPTIONS else _native.Decoder
    monkeypatch.setattr(_native, native_class.__name__, capture)
    construct()
    expected = {
        descriptor.native_name for descriptor in descriptors if descriptor.native_name is not None
    }
    assert expected <= forwarded.keys()


@pytest.mark.parametrize("descriptor", ENCODER_OPTIONS + DECODER_OPTIONS)
def test_every_choice_is_implemented_or_rejected(descriptor: object) -> None:
    if descriptor.accepted is None:
        return
    for value in descriptor.accepted:
        if descriptor.implemented is None or value in descriptor.implemented:
            descriptor.validate(value)
        else:
            with pytest.raises(NotImplementedError):
                descriptor.validate(value)


def test_float_hook_matches_functional_and_reusable_decode() -> None:
    functional_calls: list[str] = []
    reusable_calls: list[str] = []

    functional = toon.decode(b"1.25", float_hook=lambda text: functional_calls.append(text) or 5)
    reusable = toon.Decoder(float_hook=lambda text: reusable_calls.append(text) or 5).decode(
        b"1.25"
    )

    assert functional == reusable == 5
    assert functional_calls == reusable_calls == ["1.25"]


def test_float_hook_errors_propagate_unchanged() -> None:
    marker = RuntimeError("hook marker")

    def fail(text: str) -> object:
        raise marker

    for call in (
        lambda: toon.decode(b"1.25", float_hook=fail),
        lambda: toon.Decoder(float_hook=fail).decode(b"1.25"),
    ):
        with pytest.raises(RuntimeError) as caught:
            call()
        assert caught.value is marker


@pytest.mark.parametrize("entry", [toon.Encoder, toon.encode])
@pytest.mark.parametrize("order", ["sorted", "deterministic"])
def test_deferred_order_values_fail_consistently(entry: object, order: str) -> None:
    if entry is toon.Encoder:
        call = lambda: entry(order=order)
    else:
        call = lambda: entry({"b": 1, "a": 2}, order=order)
    with pytest.raises(NotImplementedError, match=f"order={order!r}"):
        call()


def test_functional_encode_reuses_only_the_default_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Capture:
        def __init__(self) -> None:
            self.values: list[object] = []

        def encode(self, value: object) -> bytes:
            self.values.append(value)
            return b"cached"

    capture = Capture()
    monkeypatch.setattr(toon, "_DEFAULT_ENCODER", capture)

    assert toon.encode({"x": 1}) == b"cached"
    assert capture.values == [{"x": 1}]
    assert toon.encode([1, 2], delimiter="|") == b"[2|]: 1|2"
    assert capture.values == [{"x": 1}]
