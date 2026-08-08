"""The functional typed path reuses lowered native plans, not codec objects."""

import msgspec
import msgspec_toon as toon
from msgspec_toon._plan import compile_native_plan


class CacheDocument(msgspec.Struct):
    value: int


def test_native_plan_is_reused_and_accepted_by_decoder() -> None:
    compile_native_plan.cache_clear()
    first = compile_native_plan(CacheDocument)
    assert compile_native_plan(CacheDocument) is first
    assert compile_native_plan.cache_parameters()["maxsize"] == 512

    decoder = toon.Decoder(CacheDocument)
    assert decoder.decode(b"value: 7") == CacheDocument(7)
