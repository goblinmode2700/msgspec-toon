# msgspec-toon

TOON (Token-Oriented Object Notation) is a line-oriented text format that
reduces repeated keys in uniform JSON-shaped data.

msgspec is a high-performance serialization and validation library whose typed
`Struct` objects are a faster, lighter alternative to Pydantic models.

`msgspec-toon` is a native TOON 4.1 codec for Python. It decodes TOON text
directly into `msgspec.Struct` objects. It does not build an intermediate
`dict` and `list` tree.

Use it when tabular data must fit in a language model context window, but the
application still needs typed Python objects and fast in-process conversion.

> This is a beta release. The project passes the pinned TOON 4.1.1 corpus, but
> it does not yet support every type that `msgspec.json` supports.

## Install

Install the public beta from PyPI:

```bash
uv add msgspec-toon
```

The package requires Python 3.13 or newer. Its only runtime dependency is the
exact pin `msgspec==0.21.1`. Benchmark codecs and tokenizers are optional
development dependencies. They are not installed with the library.

## Decode TOON into a Struct

```python
import msgspec
import msgspec_toon as toon


class Metadata(msgspec.Struct, frozen=True):
    alias: str
    region: str


class Worker(msgspec.Struct, frozen=True):
    pid: int
    provider: str
    metadata: Metadata


class Document(msgspec.Struct, frozen=True):
    workers: list[Worker]


wire = b"""workers[2]{pid,provider,metadata{alias,region}}:
  9007199254740993,claude,worker-a,west
  80916,claude,worker-b,east"""

decoder = toon.Decoder(Document)
document = decoder.decode(wire)

assert isinstance(document, Document)
assert document.workers[0].pid == 9007199254740993
assert toon.encode(document) == wire
```

The parser uses the target type while it reads the input. It constructs the
final Struct objects directly. The G2 allocation proof records zero temporary
built-in dictionaries and lists for this path.

## Read and write TOON files

The codec accepts `bytes`, `bytearray`, `memoryview`, or `str`. Encoding returns
`bytes`, so normal Python file APIs work without an adapter.

```python
from pathlib import Path

import msgspec_toon as toon


source = Path("workers.toon")
target = Path("workers-copy.toon")

decoder = toon.Decoder(Document)
encoder = toon.Encoder()

value = decoder.decode(source.read_bytes())
target.write_bytes(encoder.encode(value))
```

The conversion itself does not open files, sockets, or subprocesses. Your
application controls all I/O.

## Use untyped values

Omit `type` when you need normal Python dictionaries and lists:

```python
value = toon.decode(b"name: ada\nactive: true")
wire = toon.encode(value)
```

The public surface follows `msgspec.json` where support exists:

- `encode` and `decode`
- reusable `Encoder` and `Decoder`
- `enc_hook` and `dec_hook`
- strict decoding by default
- msgspec-compatible encode, decode, and validation errors

The encoder can use one through 16 spaces per indentation level. The decoder default is
two spaces. If you select another width, the producer and consumer must use the same
setting:

```python
wire = toon.encode(value, delimiter="\t", indent=1)
toon.decode(wire, indent_size=1)
```

If they do not match, the decode error reports the observed leading-space count and tells
the caller to pass the matching `indent_size`. Using `indent=1` can reduce tokens in nested
documents, but it makes the width an out-of-band pipeline setting. Payload shape still
decides whether TOON uses fewer tokens than compact JSON.

Decode accepts a leading UTF-8 byte order mark, Windows `CRLF` line endings, and a final
newline. These inputs normalize only while reading; encoding does not emit a byte order mark.

The functional and reusable decoders both accept `float_hook`:

```python
from decimal import Decimal

value = toon.decode(b"1.25", float_hook=Decimal)
decoder = toon.Decoder(float_hook=Decimal)

assert value == decoder.decode(b"1.25") == Decimal("1.25")
```

Typed encode and decode support these msgspec-native values:

- `datetime`, `date`, `time`, and `timedelta`
- `UUID`
- `Decimal`
- string `Enum` and integer `Enum`

The encoder normalizes these values before it calls `enc_hook`. Decimal values keep all
their digits and trailing zeroes. Typed decode constructs each value without a built-in
container tree.

```python
from decimal import Decimal
from uuid import UUID

toon.encode(Decimal("1.2300"))
# b'"1.2300"'

toon.encode(Decimal("1.2300"), decimal_format="number")
# b'1.2300'

toon.encode(UUID("12345678-1234-5678-1234-567812345678"), uuid_format="hex")
# b'"12345678123456781234567812345678"'
```

TOON 4.1 uses one canonical spelling for whole numbers. Thus, the encoder writes `1.0`
as `1`. It writes `-0.0` as `0`, as required by the official fixtures.

An untyped decode returns an `int` for these values. A typed `float` decode returns a
`float`, but it cannot recover the sign of `-0.0` because the sign is not on the wire.

The codec does not implement sorted or deterministic output. Both encoder entry
points raise `NotImplementedError` for these `order` values. They never ignore
an accepted option.

Typed decode supports recursive Structs, array-like Structs, tagged Struct unions in both object
and positional forms, `object` as an open value, unions of bool, int, float, and str, native scalar
values, and permissive scalar conversion. `object` uses the same requested open-value path as
`Any`; it does not add an intermediate tree around a typed value. Scalar unions select an exact
wire category before a widening conversion, matching msgspec when types overlap.

For a tagged `array_like` Struct, position zero is the discriminator and the declared fields
follow it. A Struct union must use one shape throughout: mixing object-form and array-like Struct
variants fails during plan construction. Set `strict=False` to accept the same bool, integer, and
float string conversions as msgspec 0.21.1. Strict mode stays the default.

Other multi-member unions remain explicit plan errors. Use a tagged Struct union for object
variants. Use `object` or `Any` when the value shape is intentionally open.

Non-string mapping keys are intentionally rejected in 0.3.0b1. See the
[mapping-key policy](https://github.com/goblinmode2700/msgspec-toon/blob/main/docs/mapping-key-policy.md).

## Why not wrap another TOON codec?

A wrapper must first convert a Struct into built-in containers. Typed decode
must parse a built-in tree and then call `msgspec.convert`. Those extra trees
can cost more than the codec work.

| Project | Format target | Typed msgspec path | Integration model |
|---|---|---|---|
| **msgspec-toon** | TOON 4.1.1 corpus | Direct Struct encode and decode | Native, in process |
| [`toon-rust`](https://github.com/toon-format/toon-rust) | TOON 3.0 | No Python msgspec path | Rust library and CLI |
| `toons` 0.7.0 | Earlier TOON grammar | Built-in tree | Python Rust extension |
| `python-toon` 0.1.3 | Earlier TOON grammar | `to_builtins` / `convert` | Pure Python and CLI |

TOON 4 nested field groups are important. They let a uniform nested record use
one tabular header:

```text
workers[2]{pid,provider,metadata{alias,region}}:
  20324,claude,worker-a,west
  80916,claude,worker-b,east
```

Older encoders can fall back to a larger entry form for the same data.

## Tokens and speed

![Empirical speed-token Pareto set](https://raw.githubusercontent.com/goblinmode2700/msgspec-toon/main/docs/assets/benchmarks/pareto-set-change.png)

The figure shows absolute end-to-end time against absolute `o200k_base` token
count. Pareto status is calculated separately for each payload shape and record
count. Lines connect the same implementation across record counts. They show
workload scaling, not an unmeasured continuous Pareto curve.

The generated [benchmark report](https://github.com/goblinmode2700/msgspec-toon/blob/main/BENCHMARKS.md) also publishes the detailed axes:

- Direct encode, decode, and total time for each measured codec.
- Absolute token counts, including compact JSON, under tiktoken `o200k_base`.

The report crosses four payload shapes with four record counts. Canonical TOON
uses more tokens than compact JSON for the measured irregular shapes.

All timing rows come from one session and one release build. The estimator is
the mean across ten independent worker processes. It never reports the minimum.
Against `v0.2.0b5`, the complete release guard found entry decode 9-24% faster,
keyed decode 9-11% faster, entry encode 11-15% faster, and untyped decode 2-8%
faster. It found no reproduced protected regression. These ranges are direct
same-session time comparisons, not ratios to an arbitrary reference row.
The raw evidence is in the
[`conformance/report.json`](https://github.com/goblinmode2700/msgspec-toon/blob/main/conformance/report.json)
file.

## Conformance and safety

- All 538 pinned TOON 4.1.1 fixtures pass in both directions.
- Typed decode creates no intermediate built-in container tree.
- Integers keep Python precision and do not route through `float`.
- Errors contain coordinates and static messages, never input payload text.
- Malformed input must return an error. It must not panic or terminate Python.
- Canonical output is byte-locked by tests.

The generated support matrix in the
[`conformance/report.json`](https://github.com/goblinmode2700/msgspec-toon/blob/main/conformance/report.json)
file lists supported, rejected, and not-yet-supported msgspec features.
Unsupported behavior fails clearly. It does not silently return a different
value.

## Optional msgspec Struct fast path

The stock package reads Struct fields through msgspec's public Python
attributes. This is the compatible path for `msgspec==0.21.1`.

The repository also contains a versioned Struct-access capsule proposal for
msgspec. You can build the same codec against that patch in an isolated
environment:

```bash
make fastpath-build
make fastpath-check
make fastpath-bench
.venv-fastpath/bin/python
```

This workflow fetches a hash-pinned msgspec commit, applies the preserved patch,
and builds both release wheels. It does not modify the normal `.venv`. The build
fails unless the capsule path is active. Published wheels do not depend on the
unreleased API.

## Develop and reproduce

Use `uv` for all Python environment work:

```bash
uv sync --locked                         # library and developer tools
make build                              # release extension in .venv
make check                              # Rust and Python checks
make qualify                            # canonical release gate and evidence
uv run python conformance/run.py        # pinned 538-fixture corpus
make g2                                 # allocation proof in a separate build

uv sync --group bench --locked           # opt in to benchmark packages
make bench                              # same-run codec and typed ladders
make public-report                      # raw JSON, R charts, and BENCHMARKS.md
```

`make public-report` uses the host `Rscript`, `ggplot2`, `jsonlite`, and
`scales`. It does not install R or add R packages to the Python environment.
The [release guide](https://github.com/goblinmode2700/msgspec-toon/blob/main/docs/releasing.md)
documents installed-artifact verification and Trusted Publishing.

## License

[MIT](https://github.com/goblinmode2700/msgspec-toon/blob/main/LICENSE)
