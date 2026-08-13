"""Release-regression probes for non-tabular untyped decode shapes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import build_freshness  # noqa: F401  (refuses stale or instrumented builds)
import msgspec_toon
from _timing import measure
from payloads import irregular_records_tree, nested_mixed_tree


def sample_run(records: int) -> dict[str, Any]:
    """Measure both ordinary-object shapes; metric selection skips the other."""
    nested_wire = msgspec_toon.encode(nested_mixed_tree(records))
    irregular_wire = msgspec_toon.encode(irregular_records_tree(records))
    decoder = msgspec_toon.Decoder()
    return {
        "records": records,
        "decode_us": {
            "nested_records": measure(
                "decode.nested_records", lambda: decoder.decode(nested_wire)
            ).us,
            "irregular": measure("decode.irregular", lambda: decoder.decode(irregular_wire)).us,
        },
    }
