# msgspec-toon

**The goal, stated precisely:** the most **token-efficient** and **fastest** TOON 4.1
codec for Python, integrated natively with **msgspec 0.21.1** — the way `msgspec.json`
works, not the way the wrapper-shaped `msgspec.toml` works. The typed path decodes TOON
text **directly into `msgspec.Struct` instances with zero intermediate dict/list tree**,
and encodes Structs by reading their fields directly, never through
`msgspec.to_builtins`. Both target metrics are measured, gated, and published — never
asserted.

TOON (Token-Oriented Object Notation) exists to cost fewer LLM tokens than JSON. Its
entire saving lives in the tabular array with nested field groups — a spec-4.0
construct no other Python codec emits:

```text
workers[2]{pid,provider,metadata{alias,region}}:      # TOON 4.1 (this codec): 527 B, 238 tokens
  20324,claude,worker-a,west
  80916,claude,worker-b,east

# the same value in compact JSON: 1,339 B, 372 tokens
# the same value from the existing Python TOON codecs (v3.0-era fallback form):
#   1,482 B, 467 tokens — MORE than the JSON they replace
```

## Measured results (v0.2.0, all from `conformance/report.json`)

Every number below regenerates with `make report`; the machine-readable evidence, with
tokenizer versions, corpus commit, and methodology, ships in the report.

**Conformance** — the official TOON 4.1 fixture corpus (`toon-format/spec` v4.1.1,
commit-pinned and hash-locked, 538 tests): **all 538 pass, both directions, zero
declared divergences**, including tab/pipe delimiters, keyed tabular objects
(`k[N:]{fields}:`), nested field groups, strict-error and non-strict-leniency fixtures.

**Token efficiency** (tiktoken `o200k_base`):

| format | uniform records | string-heavy | numeric-heavy |
|---|---|---|---|
| **this codec (canonical)** | **0.61–0.64× JSON** | 0.80× | 0.65× |
| `toons` 0.7.0 / `python-toon` 0.1.3 | 1.25× JSON | 1.10× | 0.65×\* |

\* the incumbents only tabularize flat records; one nested field per record collapses
them to the fallback form that costs more than JSON.

The token advantage is a property of the tabular forms specifically, not of TOON:
irregular, non-uniform shapes cost **1.16–1.19×** compact JSON's tokens (their smaller
byte count tokenizes worse per byte), and the spec requires the entry-by-entry fallback
for them, so no encoder change recovers it — keep those payloads JSON when tokens are
the budget. The spec-legal `indent=1` option saves tokens on every shape (uniform@4096:
0.62× → **0.58×**). Mechanism, measurements, and the closed spec rulings:
`docs/token-shape-guidance.md`.

**Speed** (same-run, Apple silicon, abi3 release wheel, min-of-batches):

- Typed decode (`Decoder(T).decode`) beats untyped-decode-plus-`msgspec.convert` at
  every payload size (G3), and beats the incumbent production pipeline
  (`python_toon.decode` + `convert` / `to_builtins` + `python_toon.encode`) by
  **19–51×**.
- Raw codec floor (G5): **2–6.5× faster than `toons`** (Rust) and **~20× faster than
  `python-toon`** in both directions at every size — while emitting 2.9× fewer bytes.
- The no-tree claim is proven by allocation counters: a typed decode of a 64-record
  document creates **0** intermediate dicts/lists; the wrapper shape creates 129.
- Honest miss (G4): the whole typed encode does not yet beat `msgspec.to_builtins`
  *alone* (2.2× at 16 records, ~10% at 4096) — public stable-ABI attribute reads
  cannot match msgspec's private C slot access. Reported in every release, not masked.

## Usage

```python
import msgspec
import msgspec_toon as toon  # drop-in for `from msgspec import json as toon`


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


text = b"""workers[2]{pid,provider,metadata{alias,region}}:
  9007199254740993,claude,worker-a,west
  80916,claude,worker-b,east"""

doc = toon.decode(text, type=Document)  # -> Document, no intermediate tree
assert doc.workers[0].pid == 9007199254740993  # ints at Python precision, always
assert toon.encode(doc) == text  # byte-exact canonical round-trip

toon.decode(text)  # untyped: dict/list, like json.loads
toon.Decoder(Document)
toon.Encoder()  # reusable, plan-cached

# The only wire options are the ones TOON 4.1 itself defines (spelled in the
# wire, defaults byte-identical to canonical output):
toon.encode(value, delimiter="\t")  # [N\t] headers, tab-separated cells
toon.encode(value, indent=4)
toon.decode(buf, indent_size=4)
```

API surface mirrors `msgspec.json`: `encode`, `decode(type=...)`, `Encoder`,
`Decoder`, `enc_hook`/`dec_hook`, `strict=True` default, `DecodeError` /
`ValidationError` (msgspec subclasses carrying `.line`/`.column`/`.code` — and, by
hard requirement, **never any payload content**).

## Design commitments

- **Runtime dependencies: exactly `msgspec==0.21.1`.** The typed machinery compiles
  plans from `msgspec.inspect` through a single adapter module; a msgspec metadata
  change touches one file.
- **Rust + PyO3, `abi3-py313`** stable-ABI wheels; Python ≥ 3.13.
- **In-process only**: a conversion opens no file, socket, or subprocess.
- **Streaming decode**: the input buffer is borrowed, never copied whole.
- **Canonical by default**: two default-constructed encoders always produce identical
  bytes; only spec-defined, wire-declared options exist.
- **Evidence over claims**: conformance counts, allocation proofs, same-run speed
  ladders, token counts under named tokenizers, and a frozen-baseline optimization
  ledger all live in the generated report.

## Development

```bash
uv sync                        # env (14-day dependency cooldown enforced natively)
make check                     # ruff + rustfmt + clippy -D warnings + mypy strict
                               #   + 32 Rust tests + 43 Python tests
make bench                     # speed ladders vs toons/python-toon/msgspec.json
uv run python benches/bench_tokens.py     # token gates (tiktoken o200k_base)
uv run python conformance/run.py          # the 538-test official corpus
make baseline && make ab       # same-session A/B vs the frozen v0.1.0 wheel
make report                    # regenerate conformance/report.json
make audit                     # dependency-age cooldown check (network)
```

To build the optional upstream Struct-access fast path in an isolated environment:

```bash
make fastpath-build            # patched msgspec + msgspec-toon release wheels
make fastpath-check            # protected tests and corpus through the capsule path
make fastpath-bench            # same-binary capsule/fallback measurement
make fastpath-gates            # normal G3/G4 ladder; G4 currently exits nonzero at 4-64
.venv-fastpath/bin/python      # run Python with the activated build
```

This profile fetches the hash-pinned msgspec 0.21.1 source, applies the preserved public
C-API patch, and installs both wheels into `.venv-fastpath`. It does not modify `.venv`,
the lockfile, or the published `msgspec==0.21.1` requirement. `fastpath-build` exits if the
Encoder does not report the `capsule` backend.

Truth lives in `openspec/specs/` (requirements, validated), `docs/` (the design of
record), `HANDOFF.md` (current state + open items), and `conformance/report.json`
(the evidence). Contributor context for coding agents is in `CLAUDE.md` /
`AGENTS.md`.

## Status and lineage

`v0.0.1-poc` → `v0.1.0-conformant` (zero fixture failures) → **`v0.2.0`** (perfect
538/538 corpus, wire options, token measurement, optimization round: typed decode
−15…−24% vs the frozen baseline). Open work is enumerated honestly in `HANDOFF.md` —
headline items: the G4 encode gap (candidate E3 pending), typed Tier 1/2 type support,
multi-platform wheels/CI, and an adversarial review sweep of the newest hot-path code.
