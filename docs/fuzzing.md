# Native fuzzing

The fuzz workspace is separate from the runtime crate. It uses cargo-fuzz 0.13.2 and nightly
Rust. Normal builds do not compile libFuzzer or add a runtime dependency.

Generate the deterministic parser seeds. The command also removes learned corpus entries so the
checked-in corpus stays reproducible:

```bash
uv run python scripts/seed_fuzz_corpus.py
```

Build and run the bounded smoke tests:

```bash
cargo +nightly-2026-07-15 fuzz build --fuzz-dir fuzz
cargo +nightly-2026-07-15 fuzz run parser_bytes --fuzz-dir fuzz -- -max_total_time=30
cargo +nightly-2026-07-15 fuzz run integer_list_roundtrip --fuzz-dir fuzz -- -max_total_time=30
```

The first target sends arbitrary bytes directly to the pure-Rust parser. Invalid UTF-8 must return
an error. The second target creates bounded integer lists, emits canonical TOON, decodes it through
the parser, emits it again, and checks value and byte stability.

Keep only minimized reproductions. Add each confirmed defect to the permanent test suite before a
fix.
