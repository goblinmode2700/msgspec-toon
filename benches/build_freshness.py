"""Refuse to measure a stale or instrumented extension.

Two ways a measurement can quietly describe code that is not the code under
test, both observed in this repository:

1. **Staleness.** `.venv` installs the project editable, so `uv run` imports
   `python/msgspec_toon/_native.abi3.so` — whatever `maturin develop` last
   wrote there. A `uv pip install` of a freshly built wheel is undone by the
   next `uv run` that re-syncs. A benchmark then reports the previous build's
   numbers with no visible sign of it.
2. **Instrumentation.** An `alloc-stats` wheel (`make g2`) carries counters the
   release wheel does not. Timings taken against it are not release numbers.

Both are checked here rather than trusted, because both failure modes produce
plausible output. Import this module from anything that publishes a number.
"""

from __future__ import annotations

import os
import pathlib

from msgspec_toon import _native

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE_GLOBS = ("src/*.rs", "Cargo.toml", "Cargo.lock")
ALLOW_INSTRUMENTED_ENV = "MSGSPEC_TOON_MEASURE_INSTRUMENTATION"


def newest_source_change() -> tuple[float, pathlib.Path | None]:
    newest = 0.0
    culprit: pathlib.Path | None = None
    for pattern in SOURCE_GLOBS:
        for path in REPO.glob(pattern):
            stamp = path.stat().st_mtime
            if stamp > newest:
                newest, culprit = stamp, path
    return newest, culprit


def measuring_instrumentation() -> bool:
    """The one legitimate reason to time an instrumented build: measuring what
    the instrumentation itself costs. `benches/ab.py --allow-instrumented`
    sets this, and records in its artifact that a side was not a release
    build, so the escape can never be silent."""
    return os.environ.get(ALLOW_INSTRUMENTED_ENV) == "1"


def require_current_release_build() -> None:
    """Exit with instructions rather than publish a misleading measurement.

    Staleness is only checkable — and only meaningful — for the editable
    artifact under `<repo>/python/`, which is supposed to track the working
    tree. The instrumented `.venv-g2` build is managed separately by `make g2`.
    """
    extension = pathlib.Path(_native.__file__)
    tracks_working_tree = extension.is_relative_to(REPO / "python")
    if tracks_working_tree:
        built_at = extension.stat().st_mtime
        changed_at, culprit = newest_source_change()
        if changed_at > built_at:
            raise SystemExit(
                f"stale extension: {culprit.name if culprit else 'a source file'} is newer "
                f"than {extension.name}. Run `make build` before measuring."
            )
    if hasattr(_native, "alloc_stats") and not measuring_instrumentation():
        raise SystemExit(
            "instrumented extension: this build carries the alloc-stats counters. "
            "Benchmarks must run against the release build — run `make build`."
        )


require_current_release_build()
