---
usf: 1
type: implementation-canvas
id: toon-native-codec
status: proposed
inputs:
  - spec.md
  - requirements.md
target:
  toon: "4.1"
  python: ">=3.13"
  msgspec: ">=0.21.1"
  implementation: "Rust + PyO3 + thin Python compatibility layer"
---

# toon-native-codec - implementation canvas

> A code-bearing architecture and proof-of-concept plan for a byte-exact TOON 4.1 codec with a direct typed path into `msgspec.Struct`.

This document is intentionally not another requirements document. `spec.md` explains why the problem matters and `requirements.md` decides whether the result qualifies. This canvas makes the engineering decisions, defines the source tree, sketches the core implementation in code, and leaves only fixture-driven completion and empirical gates to a runbook.

## 0. Verdict

**Code status:** architecture-complete and compile-shaped, but not compile-verified in this environment because a Rust toolchain and the pinned fixture checkout were not available. Every uncertain API spelling is fenced as a spike or mechanical compile pass rather than presented as executed fact.

**The singular implementation canvas can solve the architecture completely and can contain a meaningful vertical-slice implementation of the hard path. It cannot honestly claim the full result before the official fixture corpus, allocation tracing, and same-run benchmarks have executed.**

The right third-party architecture is:

1. a Rust TOON parser and canonical encoder,
2. a Rust `TypedConsumer` that consumes parser events and constructs the requested Python type directly,
3. a cached type-plan compiled from public `msgspec` inspection metadata,
4. a Rust `PythonValueEncoder` that reads `msgspec.Struct` fields directly,
5. a thin Python package named `msgspec_toon` whose surface mirrors `msgspec.json`, and
6. a conformance and benchmark harness that turns every release claim into a generated report.

The wrong architecture is a fast codec wrapped in `msgspec.convert`. That remains a wrapper and cannot satisfy the no-intermediate-tree requirement. The other wrong architecture is a third-party distribution that installs files inside the `msgspec` package. `msgspec.toon` is an upstream destination, not a safe third-party packaging trick.

### How much is codeable now?

| Portion | Confidence | What belongs in this canvas |
|---|---:|---|
| Source tree, packaging, API, error model, plan cache | 95% | Full code or near-full code |
| Streaming scanner, scalar parser, header/nested-field parser | 85% | Full design and implementation skeleton; complete by fixture iteration |
| Canonical encoder and tabular-shape classifier | 80% | Full algorithm and representative code |
| Direct `Struct` decoding without a dict tree | 80% | Complete vertical slice and construction strategy |
| Full `msgspec` type semantics | 55% | Plan IR and staged support matrix; long tail remains |
| Byte-exact 4.1 conformance | Unknown until run | Fixture-driven runbook, never asserted from inspection |
| Required speed floors | Unknown until run | Benchmark gates, never asserted from architecture |

A realistic first implementation can put roughly **two thirds of the production code shape** in one canvas. The remaining third is not vague “finish the parser” labor. It is explicitly divided into conformance gaps, type-system coverage, performance tuning, and release engineering.

## 1. Non-negotiable architectural decisions

### AD-001 · Route B, but through the public constructor

Use the design-of-record’s Route B: reimplement the typed decode machinery around a native TOON parser. Do **not** mirror `msgspec`’s private object layout in a third-party wheel.

The direct typed path is:

```text
TOON input buffer
  -> zero-copy line scanner
  -> structural parser
  -> borrowed Rust events / cells
  -> TypedConsumer guided by TypePlan
  -> final Python scalars and final collection objects
  -> msgspec.Struct class call with already-validated field values
```

There is no complete `dict`/`list` representation between parser and target. Final collection fields, such as a `list[Worker]`, are allowed because they are part of the requested result rather than a disposable translation tree.

Why use the class constructor rather than private slot offsets?

- It works for ordinary, frozen, keyword-only, defaulted, and post-init Structs through the public Python object model.
- It does not bind the wheel to private `msgspec` C structures.
- It is compatible with an `abi3` distribution.
- It keeps the proof of concept honest: if public construction is too slow, that is evidence for upstreaming rather than a reason to ship ABI glass.

### AD-002 · Parser and builders are separate

The parser never knows about Python or `msgspec`. It emits structural operations into a Rust trait. Three consumers share it:

- `UntypedConsumer`: constructs normal Python `dict`/`list` values for `type=Any`.
- `TypedConsumer`: constructs the requested target directly.
- `ValidationConsumer`: validates fixtures and syntax without producing a value.

Do not expose one Python object per event. Events are Rust values, often borrowing slices from the input.

### AD-003 · The type plan is a compatibility membrane

`msgspec.inspect` is powerful enough to describe Struct fields, encoded names, defaults, tags, unions, and constraints, but it is an experimental public API. Isolate it in one Python module, normalize it to a deliberately small plan schema, and pass that schema into Rust.

```text
msgspec annotation
  -> Python plan compiler
  -> normalized immutable PlanSpec
  -> Rust CompiledPlan
```

No parser or decoder code imports `msgspec.inspect` directly. A future metadata change alters the adapter, not the codec.

### AD-004 · Encoding reads values directly

The native encoder walks Python values directly. For a `msgspec.Struct`, it uses a cached `EncodePlan` and field access. It never calls `msgspec.to_builtins`.

For arrays of Structs, tabular eligibility is derived from the field plans and checked against runtime values. Nested Struct fields become nested field groups when every row has the same nested shape and all leaves are encodable primitives.

### AD-005 · Canonical output has no wire knobs

The public API may mirror `msgspec.json` options that transform unsupported values or establish ordering, but it exposes no delimiter, indentation, number-style, or table-preference options. The output profile is fixed by TOON 4.1.

### AD-006 · `strict` controls both wire and coercion tolerance

`strict=True` is the default and means:

- all TOON strict-mode checks run,
- malformed or noncanonical forms raise,
- typed coercions use msgspec-compatible strict rules.

`strict=False` enables only a documented set of parser tolerances and compatible typed coercions. It never suppresses an error silently.

### AD-007 · Errors retain coordinates, not payload

Internal failures carry machine data only:

```rust
pub struct Fault {
    pub code: FaultCode,
    pub line: u32,
    pub column: Option<u32>,
    pub path: SmallPath,
}
```

No fault stores a source line, token spelling, key, cell, or value. User-facing text is formatted from static templates plus coordinates and structural path components. Payload-derived values cannot leak because they never enter the exception object.

### AD-008 · `abi3-py313` is the initial wheel target

The project already targets Python 3.13 or newer. Start with PyO3’s `abi3-py313` feature. This gives one wheel per operating-system/architecture family while preserving access to the Python 3.13 limited API.

Do not optimize against a full-ABI development build and then assume the stable-ABI wheel has the same result. Bench the release wheel itself.

## 2. Package and repository layout

```text
toon-native-codec/
├── pyproject.toml
├── Cargo.toml
├── Cargo.lock
├── LICENSE
├── README.md
├── python/
│   └── msgspec_toon/
│       ├── __init__.py
│       ├── __init__.pyi
│       ├── _plan.py
│       ├── _types.py
│       └── py.typed
├── src/
│   ├── lib.rs
│   ├── api.rs
│   ├── buffer.rs
│   ├── error.rs
│   ├── scalar.rs
│   ├── scan.rs
│   ├── header.rs
│   ├── parser.rs
│   ├── event.rs
│   ├── untyped.rs
│   ├── plan.rs
│   ├── typed.rs
│   ├── shape.rs
│   ├── encode.rs
│   └── writer.rs
├── tests/
│   ├── test_api.py
│   ├── test_errors.py
│   ├── test_large_ints.py
│   ├── test_nested_groups.py
│   ├── test_typed_allocations.py
│   ├── test_typed_roundtrip.py
│   └── test_fixtures.py
├── benches/
│   ├── bench_codecs.py
│   ├── bench_typed.py
│   ├── bench_allocations.py
│   └── payloads.py
├── conformance/
│   ├── fixtures.lock.json
│   ├── fetch.py
│   ├── run.py
│   ├── schema.json
│   └── report.example.json
├── scripts/
│   ├── check-no-io.py
│   ├── inspect-wheel.py
│   └── release-report.py
└── .github/
    └── workflows/
        ├── ci.yml
        ├── wheels.yml
        └── release.yml
```

### Crate boundaries

A single crate is enough for the first implementation, but keep module boundaries as if `toon_core` could later be extracted. The parser, scanner, scalar rules, header grammar, shape classifier, and writer must not import PyO3.

If the codebase grows beyond roughly 12,000 Rust lines, split it into:

```text
crates/toon-core       # no Python dependency
crates/toon-python     # PyO3 integration
```

Do not start with a workspace merely to decorate the directory tree.

## 3. Public Python API

The third-party import is:

```python
import msgspec_toon as toon
```

The supported substitution is:

```python
# before
from msgspec import json as codec

# after
import msgspec_toon as codec
```

The package exports:

```python
encode(obj, *, enc_hook=None, order=None) -> bytes
decode(buf, *, type=Any, strict=True, dec_hook=None) -> Any
Encoder(*, enc_hook=None, decimal_format="string", uuid_format="canonical", order=None)
Decoder(type=Any, *, strict=True, dec_hook=None, float_hook=None)
DecodeError
ValidationError
EncodeError
```

`decimal_format` and `uuid_format` are accepted to preserve constructor familiarity. Their behavior is part of the staged support matrix, not an excuse to silently diverge.

### `python/msgspec_toon/__init__.py`

```python
from __future__ import annotations

from typing import Any, Callable, Final

import msgspec

from . import _native
from ._plan import compile_plan

__all__ = [
    "DecodeError",
    "Decoder",
    "EncodeError",
    "Encoder",
    "ValidationError",
    "decode",
    "encode",
]

EncodeError: Final = msgspec.EncodeError


class DecodeError(msgspec.DecodeError):
    """A TOON syntax error carrying coordinates but never source text."""

    __slots__ = ("line", "column", "code")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code


class ValidationError(msgspec.ValidationError):
    """A typed decoding error with TOON coordinates."""

    __slots__ = ("line", "column", "code")

    def __init__(
        self,
        message: str,
        *,
        line: int,
        column: int | None,
        code: str,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.code = code


def _translate_fault(exc: _native.NativeFault) -> BaseException:
    cls = ValidationError if exc.validation else DecodeError
    return cls(
        exc.safe_message,
        line=exc.line,
        column=exc.column,
        code=exc.code,
    )


class Encoder:
    __slots__ = ("_native",)

    def __init__(
        self,
        *,
        enc_hook: Callable[[Any], Any] | None = None,
        decimal_format: str | Callable[[Any], Any] = "string",
        uuid_format: str = "canonical",
        order: str | None = None,
    ) -> None:
        self._native = _native.Encoder(
            enc_hook=enc_hook,
            decimal_format=decimal_format,
            uuid_format=uuid_format,
            order=order,
        )

    def encode(self, obj: Any) -> bytes:
        try:
            return self._native.encode(obj)
        except _native.NativeFault as exc:
            raise _translate_fault(exc) from None


class Decoder:
    __slots__ = ("_native",)

    def __init__(
        self,
        type: Any = Any,
        *,
        strict: bool = True,
        dec_hook: Callable[[type, Any], Any] | None = None,
        float_hook: Callable[[str], Any] | None = None,
    ) -> None:
        plan = None if type is Any else compile_plan(type)
        self._native = _native.Decoder(
            target=type,
            plan=plan,
            strict=strict,
            dec_hook=dec_hook,
            float_hook=float_hook,
        )

    def decode(self, buf: bytes | bytearray | memoryview | str) -> Any:
        try:
            return self._native.decode(buf)
        except _native.NativeFault as exc:
            raise _translate_fault(exc) from None


def encode(
    obj: Any,
    *,
    enc_hook: Callable[[Any], Any] | None = None,
    order: str | None = None,
) -> bytes:
    return Encoder(enc_hook=enc_hook, order=order).encode(obj)


def decode(
    buf: bytes | bytearray | memoryview | str,
    *,
    type: Any = Any,
    strict: bool = True,
    dec_hook: Callable[[type, Any], Any] | None = None,
) -> Any:
    return Decoder(type, strict=strict, dec_hook=dec_hook).decode(buf)
```

**Spike S-01:** confirm that subclassing `msgspec.DecodeError` and `msgspec.ValidationError` remains supported on the pinned minimum version. If not, export package-native subclasses of `ValueError` and preserve `__cause__ = None`; do not fake identity with `msgspec.DecodeError`.

## 4. Build configuration

### `pyproject.toml`

```toml
[build-system]
requires = ["maturin>=1.9,<2"]
build-backend = "maturin"

[project]
name = "msgspec-toon"
version = "0.0.1"
description = "A native TOON 4.1 codec with direct msgspec.Struct decoding"
requires-python = ">=3.13"
dependencies = ["msgspec>=0.21.1"]
readme = "README.md"
license = { text = "MIT" }
classifiers = [
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Rust",
  "Typing :: Typed",
]

[dependency-groups]
dev = [
  "maturin>=1.9,<2",
  "pytest>=8.4",
  "pytest-benchmark>=5.1",
  "pytest-codspeed>=4.0",
  "ruff>=0.12",
  "mypy>=1.17",
]

[tool.maturin]
python-source = "python"
module-name = "msgspec_toon._native"
bindings = "pyo3"
strip = true

[tool.pytest.ini_options]
addopts = "-ra --strict-config --strict-markers"
testpaths = ["tests"]

[tool.ruff]
target-version = "py313"
line-length = 100
```

### `Cargo.toml`

```toml
[package]
name = "msgspec-toon-native"
version = "0.0.1"
edition = "2024"
rust-version = "1.88"
license = "MIT"

[lib]
name = "_native"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.29", features = ["abi3-py313"] }
memchr = "2.7"
ryu = "1.0"
smallvec = "1.15"

[profile.release]
lto = "thin"
codegen-units = 1
panic = "abort"
strip = "symbols"

[profile.bench]
inherits = "release"
debug = true
```

The runtime Python dependency tree remains only the distribution plus `msgspec`. Rust crates are compiled into the extension and do not become Python runtime packages.

## 5. Core parser contract

### Events are internal and borrowed

```rust
// src/event.rs

#[derive(Debug, Clone, Copy)]
pub enum ScalarToken<'a> {
    Null,
    Bool(bool),
    Integer(&'a [u8]),
    Float(&'a [u8]),
    BareString(&'a [u8]),
    QuotedString(&'a [u8]),
}

#[derive(Debug)]
pub enum Event<'a> {
    StartObject,
    Key(StringToken<'a>),
    EndObject,
    StartArray { declared_len: usize },
    EndArray,
    Scalar(ScalarToken<'a>),
}

#[derive(Debug, Clone, Copy)]
pub enum StringToken<'a> {
    Borrowed(&'a [u8]),
    Escaped(&'a [u8]),
}

pub trait Consumer<'py> {
    type Output;

    fn start_object(&mut self, at: Position) -> Result<(), Fault>;
    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault>;
    fn end_object(&mut self, at: Position) -> Result<(), Fault>;
    fn start_array(&mut self, len: usize, at: Position) -> Result<(), Fault>;
    fn end_array(&mut self, at: Position) -> Result<(), Fault>;
    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault>;
    fn finish(self) -> Result<Self::Output, Fault>;
}
```

A callback interface is preferable to materializing a `Vec<Event>`. The parser may use tiny stack frames internally, but it does not allocate one owned object per token.

### Input buffer

```rust
// src/buffer.rs

pub enum Input<'py> {
    Bytes(&'py [u8]),
    Utf8String(&'py str),
}

impl<'py> Input<'py> {
    pub fn as_bytes(&self) -> &[u8] {
        match self {
            Self::Bytes(value) => value,
            Self::Utf8String(value) => value.as_bytes(),
        }
    }
}
```

The PyO3 boundary should borrow `bytes`, `bytearray`, and contiguous `memoryview` inputs through the buffer protocol. A Python `str` may require CPython to realize its cached UTF-8 view, but the codec does not create a second owned document buffer.

### Incremental scanner

```rust
// src/scan.rs

use memchr::memchr;

#[derive(Debug, Clone, Copy)]
pub struct Position {
    pub line: u32,
    pub column: u32,
}

#[derive(Debug, Clone, Copy)]
pub struct Line<'a> {
    pub raw: &'a [u8],
    pub content: &'a [u8],
    pub indent_spaces: usize,
    pub depth: usize,
    pub position: Position,
}

pub struct Scanner<'a> {
    input: &'a [u8],
    offset: usize,
    line: u32,
    indent_size: usize,
    strict: bool,
    saw_bom: bool,
}

impl<'a> Scanner<'a> {
    pub fn new(input: &'a [u8], indent_size: usize, strict: bool) -> Self {
        Self {
            input,
            offset: 0,
            line: 0,
            indent_size,
            strict,
            saw_bom: false,
        }
    }

    pub fn next_line(&mut self) -> Result<Option<Line<'a>>, Fault> {
        loop {
            if self.offset >= self.input.len() {
                return Ok(None);
            }

            let tail = &self.input[self.offset..];
            let width = memchr(b'\n', tail).unwrap_or(tail.len());
            let mut raw = &tail[..width];
            self.offset += width + usize::from(width < tail.len());
            self.line += 1;

            if self.line == 1 && raw.starts_with(b"\xEF\xBB\xBF") {
                raw = &raw[3..];
                self.saw_bom = true;
            }
            if raw.ends_with(b"\r") {
                raw = &raw[..raw.len() - 1];
            }

            let mut indent = 0usize;
            while indent < raw.len() && raw[indent] == b' ' {
                indent += 1;
            }

            if indent < raw.len() && raw[indent] == b'\t' && self.strict {
                return Err(Fault::syntax(
                    FaultCode::TabIndent,
                    self.line,
                    Some((indent + 1) as u32),
                ));
            }
            if self.strict && indent % self.indent_size != 0 {
                return Err(Fault::syntax(
                    FaultCode::InvalidIndent,
                    self.line,
                    Some(1),
                ));
            }

            let mut end = raw.len();
            while end > indent && raw[end - 1] == b' ' {
                end -= 1;
            }
            let content = &raw[indent..end];

            if content.is_empty() || content.starts_with(b"#") {
                continue;
            }

            return Ok(Some(Line {
                raw,
                content,
                indent_spaces: indent,
                depth: indent / self.indent_size,
                position: Position {
                    line: self.line,
                    column: (indent + 1) as u32,
                },
            }));
        }
    }
}
```

The production scanner additionally records blank-line positions needed by strict array validation, accepts tab indentation only under the documented non-strict rules, and never stores the blank line’s content.

## 6. Header and nested field-group parser

TOON 4.1’s value depends on nested field groups, so this grammar is core rather than an enhancement.

```rust
// src/header.rs

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Delimiter {
    Comma,
    Tab,
    Pipe,
}

impl Delimiter {
    pub fn byte(self) -> u8 {
        match self {
            Self::Comma => b',',
            Self::Tab => b'\t',
            Self::Pipe => b'|',
        }
    }
}

#[derive(Debug, Clone)]
pub struct FieldNode<'a> {
    pub name: StringToken<'a>,
    pub children: Vec<FieldNode<'a>>,
}

#[derive(Debug, Clone)]
pub struct Header<'a> {
    pub key: Option<StringToken<'a>>,
    pub declared_len: usize,
    pub delimiter: Delimiter,
    pub keyed: bool,
    pub fields: Vec<FieldNode<'a>>,
    pub inline_values: Option<&'a [u8]>,
}

pub fn parse_header<'a>(
    content: &'a [u8],
    default_delimiter: Delimiter,
    strict: bool,
    at: Position,
) -> Result<Option<Header<'a>>, Fault> {
    let bracket_start = find_unquoted(content, b'[', 0);
    let Some(bracket_start) = bracket_start else {
        return Ok(None);
    };

    if let Some(colon) = find_unquoted(content, b':', 0) {
        if colon < bracket_start {
            return Ok(None);
        }
    }

    let bracket_end = find_unquoted(content, b']', bracket_start + 1)
        .ok_or_else(|| Fault::syntax(FaultCode::UnclosedBracket, at.line, None))?;

    let key = if bracket_start == 0 {
        None
    } else {
        Some(parse_string_token(&content[..bracket_start], at)?)
    };

    let (declared_len, delimiter, keyed) =
        parse_bracket(&content[bracket_start + 1..bracket_end], default_delimiter, at)?;

    let mut cursor = bracket_end + 1;
    let fields = if content.get(cursor) == Some(&b'{') {
        let close = find_matching_brace(content, cursor)
            .ok_or_else(|| Fault::syntax(FaultCode::UnclosedFieldGroup, at.line, None))?;
        let parsed = parse_field_group(&content[cursor + 1..close], delimiter, strict, at)?;
        cursor = close + 1;
        parsed
    } else {
        Vec::new()
    };

    if content.get(cursor) != Some(&b':') {
        return Ok(None);
    }
    cursor += 1;

    let inline_values = trim_spaces(&content[cursor..]);
    let inline_values = (!inline_values.is_empty()).then_some(inline_values);

    if !fields.is_empty() && inline_values.is_some() {
        return Err(Fault::syntax(
            FaultCode::ContentAfterFieldsHeader,
            at.line,
            Some((cursor + 1) as u32),
        ));
    }
    if keyed && fields.is_empty() {
        return Err(Fault::syntax(
            FaultCode::KeyedHeaderWithoutFields,
            at.line,
            None,
        ));
    }

    Ok(Some(Header {
        key,
        declared_len,
        delimiter,
        keyed,
        fields,
        inline_values,
    }))
}

fn parse_field_group<'a>(
    content: &'a [u8],
    delimiter: Delimiter,
    strict: bool,
    at: Position,
) -> Result<Vec<FieldNode<'a>>, Fault> {
    let mut fields = Vec::new();
    let mut cursor = 0usize;
    let mut seen = Vec::<StringToken<'a>>::new();

    while cursor <= content.len() {
        let end = find_field_separator(content, cursor, delimiter.byte())
            .unwrap_or(content.len());
        let entry = trim_spaces(&content[cursor..end]);
        if entry.is_empty() {
            return Err(Fault::syntax(FaultCode::EmptyField, at.line, None));
        }

        let group_start = find_unquoted(entry, b'{', 0);
        let (name, children) = if let Some(group_start) = group_start {
            let group_end = find_matching_brace(entry, group_start)
                .ok_or_else(|| Fault::syntax(FaultCode::UnclosedFieldGroup, at.line, None))?;
            if group_end + 1 != entry.len() {
                return Err(Fault::syntax(
                    FaultCode::ContentAfterFieldGroup,
                    at.line,
                    None,
                ));
            }
            (
                parse_string_token(trim_spaces(&entry[..group_start]), at)?,
                parse_field_group(
                    &entry[group_start + 1..group_end],
                    delimiter,
                    strict,
                    at,
                )?,
            )
        } else {
            (parse_string_token(entry, at)?, Vec::new())
        };

        if strict && seen.iter().any(|prior| token_eq(*prior, name)) {
            return Err(Fault::syntax(
                FaultCode::DuplicateField,
                at.line,
                None,
            ));
        }
        seen.push(name);
        fields.push(FieldNode { name, children });

        if end == content.len() {
            break;
        }
        cursor = end + 1;
    }

    Ok(fields)
}
```

Production completion items are finite and fixture-driven: quoted keys, escape-aware scanning, delimiter mismatch detection, exact whitespace rules, overflow-safe lengths, and non-strict duplicate last-write-wins behavior.

## 7. Scalar parsing and canonical formatting

### Decoding

Do not parse every scalar as a Python string first. Classify borrowed bytes, then create exactly the requested final Python value.

```rust
pub fn classify_scalar(token: &[u8], quoted: bool) -> ScalarToken<'_> {
    if quoted {
        return ScalarToken::QuotedString(token);
    }
    match token {
        b"null" => ScalarToken::Null,
        b"true" => ScalarToken::Bool(true),
        b"false" => ScalarToken::Bool(false),
        _ if is_integer_literal(token) => ScalarToken::Integer(token),
        _ if is_float_literal(token) => ScalarToken::Float(token),
        _ => ScalarToken::BareString(token),
    }
}
```

Python integers are constructed from the full decimal token. Never route through `f64`, JavaScript, or a fixed-width Rust integer except as a fast path after a checked length/range test.

### Encoding

- `bool` is checked before `int` because Python booleans are integer subclasses.
- finite floats use TOON’s canonical range and notation rules.
- `-0.0` emits `0`.
- Python `int` uses exact decimal conversion at arbitrary precision.
- non-finite floats raise `EncodeError`.
- strings quote only when the 4.1 grammar requires it and use only the 4.1 escape set.

A scalar-sized temporary decimal string is acceptable. The requirement forbids a full copied object tree and a full copied input document, not bounded scalar formatting buffers.

## 8. Type-plan IR

The first version should support the types that matter to the challenge before attempting every feature in `msgspec`.

```python
# python/msgspec_toon/_types.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class FieldSpec:
    python_name: str
    wire_name: str
    plan: PlanSpec
    required: bool
    default: Any
    has_default_factory: bool


@dataclass(frozen=True, slots=True)
class PlanSpec:
    kind: Literal[
        "any",
        "none",
        "bool",
        "int",
        "float",
        "str",
        "list",
        "tuple_var",
        "tuple_fixed",
        "dict",
        "struct",
        "union",
        "literal",
        "custom",
    ]
    python_type: Any = None
    item: PlanSpec | None = None
    key: PlanSpec | None = None
    value: PlanSpec | None = None
    items: tuple[PlanSpec, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    tag_field: str | None = None
    tag_value: Any = None
    array_like: bool = False
    forbid_unknown_fields: bool = False
    constraints: tuple[tuple[str, Any], ...] = ()
```

### Plan compiler boundary

```python
# python/msgspec_toon/_plan.py

from __future__ import annotations

from functools import lru_cache
from typing import Any

import msgspec.inspect as mi

from ._types import FieldSpec, PlanSpec


@lru_cache(maxsize=512)
def compile_plan(annotation: Any) -> PlanSpec:
    return _lower(mi.type_info(annotation))


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
            return PlanSpec("list", item=_lower(item))
        case mi.VarTupleType(item_type=item):
            return PlanSpec("tuple_var", item=_lower(item))
        case mi.TupleType(item_types=items):
            return PlanSpec("tuple_fixed", items=tuple(map(_lower, items)))
        case mi.DictType(key_type=key, value_type=value):
            return PlanSpec("dict", key=_lower(key), value=_lower(value))
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
                        python_name=field.name,
                        wire_name=field.encode_name,
                        plan=_lower(field.type),
                        required=field.required,
                        default=field.default,
                        has_default_factory=field.default_factory is not None,
                    )
                    for field in fields
                ),
                tag_field=tag_field,
                tag_value=tag,
                array_like=array_like,
                forbid_unknown_fields=forbid_unknown_fields,
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
        (name, value)
        for name in names
        if (value := getattr(info, name, None)) is not None
    )
```

The exact `msgspec.inspect` class and attribute names must be verified against the pinned minimum version. That is a narrow adapter task, not an architectural uncertainty.

### Rust compiled plan

```rust
pub enum PlanKind {
    Any,
    None,
    Bool,
    Int(IntConstraints),
    Float(FloatConstraints),
    Str(StrConstraints),
    List(Box<CompiledPlan>),
    TupleVar(Box<CompiledPlan>),
    TupleFixed(Vec<CompiledPlan>),
    Dict(Box<CompiledPlan>, Box<CompiledPlan>),
    Struct(StructPlan),
    Union(Vec<CompiledPlan>),
    Literal(Vec<Py<PyAny>>),
    Custom(Py<PyAny>),
}

pub struct StructPlan {
    pub class: Py<PyAny>,
    pub fields: Vec<StructFieldPlan>,
    pub by_wire_name: HashMap<Vec<u8>, usize>,
    pub tag: Option<TagPlan>,
    pub array_like: bool,
    pub forbid_unknown_fields: bool,
}

pub struct StructFieldPlan {
    pub python_name: Py<PyString>,
    pub wire_name: Vec<u8>,
    pub value: CompiledPlan,
    pub default: DefaultPlan,
}
```

Plan compilation is paid once per `Decoder` instance and cached weakly by annotation identity where safe.

## 9. Direct typed construction

### Core invariant

For a Struct target, the builder stores one optional final value per field. It never stores a mapping from field names to values.

```rust
struct StructFrame {
    plan_id: PlanId,
    values: Vec<Option<Py<PyAny>>>,
    seen: BitSet,
    current_field: Option<usize>,
    at: Position,
}
```

A temporary `Vec<Option<PyObject>>` is not an intermediate object tree. It is the constructor argument frame for the final object, analogous to a native decoder’s stack slots.

### Construction algorithm

```rust
fn finish_struct<'py>(
    py: Python<'py>,
    plan: &StructPlan,
    mut frame: StructFrame,
) -> PyResult<Py<PyAny>> {
    let mut positional = Vec::with_capacity(plan.fields.len());
    let mut keyword_names = Vec::new();
    let mut keyword_values = Vec::new();

    for (index, field) in plan.fields.iter().enumerate() {
        let value = match frame.values[index].take() {
            Some(value) => value,
            None => field.default.realize(py, &field.python_name)?,
        };

        if field.is_keyword_only {
            keyword_names.push(field.python_name.clone_ref(py));
            keyword_values.push(value);
        } else {
            positional.push(value);
        }
    }

    call_struct_class_vectorcall(
        py,
        &plan.class,
        &positional,
        &keyword_names,
        &keyword_values,
    )
}
```

The first compile-safe implementation may call the class with a tuple and dict. That does **not** violate the no-tree requirement because it is a shallow constructor call frame, not a document-shaped translation tree. The optimized version should use vectorcall if the limited API and PyO3 version expose it safely.

### Tabular rows are the fast path

For this input:

```toon
workers[2]{pid,provider,metadata{alias,region}}:
  20324,claude,worker-a,west
  80916,claude,worker-b,east
```

and this target:

```python
class Metadata(msgspec.Struct):
    alias: str
    region: str

class Worker(msgspec.Struct):
    pid: int
    provider: str
    metadata: Metadata

class Document(msgspec.Struct):
    workers: list[Worker]
```

The decoder does this per row:

```text
cell 0 -> int -> Worker.slot[pid]
cell 1 -> str -> Worker.slot[provider]
cell 2 -> str -> nested Metadata.slot[alias]
cell 3 -> str -> nested Metadata.slot[region]
finish Metadata via constructor
finish Worker via constructor
append Worker to final workers list
```

It does not create either of these:

```python
{"pid": 20324, "provider": "claude", "metadata": {"alias": "worker-a", "region": "west"}}
[that_dict, another_dict]
```

### Field matching

- Match TOON keys to `wire_name`, not Python attribute name.
- Unknown fields are skipped only when the target allows them and the parser can consume their complete value without materializing it.
- Duplicate keys fail in strict mode before overwriting a field slot.
- Missing required fields fail at the closing boundary.
- Defaults and default factories are realized only for absent fields.
- Tagged unions choose a candidate as early as the tag field permits.

## 10. Typed support ladder

Implement in this order. Each rung has its own tests and benchmark payloads.

### Tier 0 · Challenge-shaped path

- `None`, `bool`, `int`, `float`, `str`
- `list[T]`
- nested `msgspec.Struct`
- `Optional[T]`
- root Struct and root `list[Struct]`
- renamed fields
- required/default fields
- nested field groups in tabular rows

This tier is sufficient to prove or disprove the architecture against the document shape in the design of record.

### Tier 1 · Common msgspec path

- fixed and variable tuples
- `dict[str, T]`
- literals
- simple tagged Struct unions
- `forbid_unknown_fields`
- `array_like` Structs
- integer/string/collection constraints
- `UNSET`

### Tier 2 · Compatibility path

- enums
- datetime/date/time/timedelta
- UUID
- Decimal
- bytes-like encodings
- named tuples
- dataclasses and attrs classes if the public promise includes them
- custom types through `dec_hook`
- complex unions and constrained annotations

A release must document its supported type matrix. It must not imply full `msgspec.json` type compatibility before Tier 2 passes differential tests.

## 11. Canonical encoder architecture

### Direct Python adapter

```rust
pub enum ValueRef<'py> {
    Null,
    Bool(bool),
    Int(Bound<'py, PyAny>),
    Float(f64),
    Str(Bound<'py, PyString>),
    Sequence(Bound<'py, PyAny>),
    Mapping(Bound<'py, PyAny>),
    Struct {
        value: Bound<'py, PyAny>,
        plan: Arc<EncodePlan>,
    },
}
```

Classification order is deliberate:

1. exact singleton/null,
2. bool,
3. int,
4. float,
5. str,
6. Struct,
7. supported sequence,
8. supported mapping,
9. `enc_hook`,
10. `EncodeError`.

### Shape classifier

```rust
pub enum FieldShape {
    Leaf { name: EncodedKey },
    Group { name: EncodedKey, children: Vec<FieldShape> },
}

pub struct TableShape {
    pub fields: Vec<FieldShape>,
    pub leaf_count: usize,
}

pub fn classify_struct_rows(
    rows: &[Bound<'_, PyAny>],
    plan_cache: &mut EncodePlanCache,
) -> PyResult<Option<TableShape>> {
    let Some(first) = rows.first() else {
        return Ok(None);
    };
    let first_type = first.get_type();

    if rows.iter().any(|row| !row.get_type().is(&first_type)) {
        return Ok(None);
    }

    let plan = plan_cache.for_struct_type(&first_type)?;
    build_table_shape_from_struct_plan(&plan, rows)
}
```

The recursive classifier returns `None` when any column is mixed, any nested group is empty, or any leaf is not a TOON primitive after hook normalization. The encoder then uses list/object fallback exactly as the spec directs.

### Row emission

Do not create `Vec<PyObject>` leaves for every row. Walk the `FieldShape` recursively and write each leaf immediately.

```rust
fn write_row(
    writer: &mut Writer,
    row: &Bound<'_, PyAny>,
    fields: &[FieldShape],
    delimiter: u8,
) -> PyResult<()> {
    let mut first = true;
    for field in fields {
        write_field_leaves(writer, row, field, delimiter, &mut first)?;
    }
    writer.newline();
    Ok(())
}
```

### Canonical output writer

```rust
pub struct Writer {
    out: Vec<u8>,
}

impl Writer {
    pub fn with_capacity(capacity: usize) -> Self {
        Self { out: Vec::with_capacity(capacity) }
    }

    pub fn bytes(&mut self, value: &[u8]) {
        self.out.extend_from_slice(value);
    }

    pub fn byte(&mut self, value: u8) {
        self.out.push(value);
    }

    pub fn indent(&mut self, depth: usize) {
        self.out.resize(self.out.len() + depth * 2, b' ');
    }

    pub fn newline(&mut self) {
        self.out.push(b'\n');
    }

    pub fn finish(mut self) -> Vec<u8> {
        if self.out.last() == Some(&b'\n') {
            self.out.pop();
        }
        self.out
    }
}
```

Whether the canonical root form ends with LF must be determined by the fixture corpus, not taste. `finish` is adjusted to the corpus result.

## 12. Fault model

```rust
// src/error.rs

#[derive(Debug, Clone, Copy)]
pub enum FaultCode {
    InvalidUtf8,
    TabIndent,
    InvalidIndent,
    DepthJump,
    UnexpectedDedent,
    UnclosedQuote,
    InvalidEscape,
    UnclosedBracket,
    InvalidLength,
    UnclosedFieldGroup,
    EmptyField,
    DuplicateField,
    DelimiterMismatch,
    ContentAfterFieldsHeader,
    KeyedHeaderWithoutFields,
    WrongRowWidth,
    WrongArrayLength,
    DuplicateKey,
    UnknownField,
    MissingField,
    TypeMismatch,
    ConstraintViolation,
    TrailingContent,
    UnsupportedType,
}

#[derive(Debug)]
pub struct Fault {
    pub code: FaultCode,
    pub line: u32,
    pub column: Option<u32>,
    pub validation: bool,
    pub path: SmallVec<[PathPart; 8]>,
}

impl Fault {
    pub fn safe_message(&self) -> String {
        let location = match self.column {
            Some(column) => format!("line {}, column {}", self.line, column),
            None => format!("line {}", self.line),
        };
        format!("{} at {}{}", self.code.summary(), location, self.path.safe_suffix())
    }
}
```

`PathPart::Field` must store a schema-known field name from the compiled plan, not an arbitrary key read from the payload. Array indices are safe numeric metadata.

Tests must place a unique sentinel in malformed input and assert that it appears nowhere in `str(exc)`, `repr(exc)`, `exc.args`, `exc.__dict__`, slots, or native fault attributes.

## 13. PyO3 boundary sketch

```rust
// src/lib.rs

use pyo3::prelude::*;

mod api;
mod buffer;
mod encode;
mod error;
mod event;
mod header;
mod parser;
mod plan;
mod scalar;
mod scan;
mod shape;
mod typed;
mod untyped;
mod writer;

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<api::Encoder>()?;
    module.add_class::<api::Decoder>()?;
    module.add_class::<api::NativeFault>()?;
    Ok(())
}
```

```rust
// src/api.rs

#[pyclass(module = "msgspec_toon._native")]
pub struct Decoder {
    plan: Option<Arc<CompiledPlan>>,
    target: Option<Py<PyAny>>,
    strict: bool,
    dec_hook: Option<Py<PyAny>>,
    float_hook: Option<Py<PyAny>>,
}

#[pymethods]
impl Decoder {
    #[new]
    #[pyo3(signature = (*, target=None, plan=None, strict=true, dec_hook=None, float_hook=None))]
    fn new(
        py: Python<'_>,
        target: Option<Py<PyAny>>,
        plan: Option<Bound<'_, PyAny>>,
        strict: bool,
        dec_hook: Option<Py<PyAny>>,
        float_hook: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let compiled = plan
            .as_ref()
            .map(|spec| CompiledPlan::from_python(py, spec))
            .transpose()?
            .map(Arc::new);

        Ok(Self {
            plan: compiled,
            target,
            strict,
            dec_hook,
            float_hook,
        })
    }

    fn decode(&self, py: Python<'_>, buf: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let input = Input::extract(buf)?;
        let mut parser = Parser::new(input.as_bytes(), self.strict);

        match &self.plan {
            Some(plan) => {
                let consumer = TypedConsumer::new(
                    py,
                    plan,
                    self.strict,
                    self.dec_hook.as_ref(),
                    self.float_hook.as_ref(),
                );
                parser.decode(consumer).map_err(NativeFault::raise)
            }
            None => {
                let consumer = UntypedConsumer::new(py, self.float_hook.as_ref());
                parser.decode(consumer).map_err(NativeFault::raise)
            }
        }
    }
}
```

The exact PyO3 0.29 signatures should be compiled rather than trusted from memory. The architecture is stable; macro syntax is a mechanical runbook item.

## 14. Proof-of-concept acceptance slice

Before implementing the full format, the vertical slice must prove all of these in one executable test module:

1. Decode a nested-field-group table directly into `Document` / `Worker` / `Metadata` Structs.
2. Record zero intermediate row dictionaries and zero nested metadata dictionaries.
3. Encode the same Struct directly without calling `msgspec.to_builtins`.
4. Round-trip an integer greater than `2**53` exactly.
5. Raise a payload-sanitized error with line and column.
6. Produce the exact expected nested-field-group header and one row per record.
7. Beat the wrapper path on the challenge-shaped payload or explicitly fail the architectural gate.

### Representative test

```python
from __future__ import annotations

import gc
import tracemalloc

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


TEXT = b"""workers[2]{pid,provider,metadata{alias,region}}:
  9007199254740993,claude,worker-a,west
  80916,claude,worker-b,east"""


def test_vertical_slice() -> None:
    value = toon.decode(TEXT, type=Document)
    assert value.workers[0].pid == 9_007_199_254_740_993
    assert toon.encode(value) == TEXT


def test_error_never_echoes_payload() -> None:
    sentinel = "SENTINEL_8841_DO_NOT_LEAK"
    malformed = f'workers[1]{{pid}}:\n  "{sentinel}'.encode()

    try:
        toon.decode(malformed, type=Document)
    except toon.DecodeError as exc:
        assert sentinel not in str(exc)
        assert sentinel not in repr(exc)
        assert all(sentinel not in repr(item) for item in exc.args)
        assert exc.line == 2
    else:
        raise AssertionError("malformed payload was accepted")
```

### Allocation instrumentation

`tracemalloc` alone reports memory blocks, not Python object type creation. Use two complementary probes:

- a debug-only native allocation counter incremented whenever the untyped consumer allocates a `dict` or `list`, and
- a test-only instrumented consumer that publishes frame/object counters.

The release build excludes counters. The allocation report must distinguish:

```json
{
  "typed": {
    "final_lists": 1,
    "final_structs": 5,
    "intermediate_dicts": 0,
    "intermediate_lists": 0
  },
  "wrapper": {
    "final_lists": 1,
    "intermediate_dicts": 5,
    "intermediate_lists": 1
  }
}
```

The exact counts depend on the schema, but the forbidden tree nodes must be zero.

## 15. Conformance strategy

### Pinning

`conformance/fixtures.lock.json`:

```json
{
  "spec_version": "4.1",
  "repository": "toon-format/spec",
  "commit": "REPLACE_WITH_EXACT_COMMIT",
  "fixture_root": "tests/fixtures",
  "tree_sha256": "REPLACE_WITH_FETCH_RESULT"
}
```

The test runner refuses to execute if the checked-out fixture tree does not match the lock. CI never fetches a moving branch during the test job.

### Differential layers

1. **Fixture truth:** official expected bytes and values are authoritative.
2. **Reference differential:** compare against the reference TypeScript implementation at a pinned version for additional generated values.
3. **Property tests:** generated supported values satisfy value → text → value.
4. **Canonical idempotence:** canonical text satisfies text → value → text byte-for-byte.
5. **Cross-language numeric cases:** include integers outside JavaScript’s exact domain even though the reference implementation may need special handling.

Reference output never overrides a fixture. A mismatch is investigated and reported, not normalized away.

## 16. Benchmark gates

All speed claims are same-machine, same-process-session comparisons using installed release wheels.

### Required benchmark rows

```text
untyped encode: msgspec_toon vs named compiled TOON codecs
untyped decode: msgspec_toon vs named compiled TOON codecs
typed decode: direct vs toon-untyped + msgspec.convert
typed encode: direct whole encode vs msgspec.to_builtins alone
```

### Payload matrix

- 1 KiB, 10 KiB, 100 KiB, 1 MiB record arrays,
- flat Struct rows,
- one nested Struct per row,
- deeply nested non-tabular objects,
- wide rows,
- large integers,
- quoted Unicode-heavy strings,
- tagged unions,
- default-heavy Structs.

### Gate definitions

- **G1 conformance:** zero fixture divergences.
- **G2 allocation:** zero forbidden intermediate dictionaries/lists on the typed challenge payload.
- **G3 typed decode:** direct typed path is measurably faster than untyped decode plus `msgspec.convert` in the same run.
- **G4 typed encode:** whole direct encode is faster than `msgspec.to_builtins` alone in the same run.
- **G5 codec floor:** no slower than the fastest named compiled codec at every size in both directions.
- **G6 wheel parity:** the `abi3` wheel, not a local full-ABI build, clears G3-G5.

A gate miss is not massaged into a pass by selecting a favorable payload. The report publishes all ladder points.

## 17. The implementation runbook

### Phase 0 · Freeze evidence

1. Pin TOON 4.1 spec and fixture commit.
2. Copy the existing measurement payload generator into the repository.
3. Record exact Python, msgspec, Rust, PyO3, maturin, compiler, and platform versions.
4. Add an empty report conforming to `conformance/schema.json`.

**Exit:** `uv run python conformance/run.py` fails only because the codec does not exist, not because fixtures are moving or undiscoverable.

### Phase 1 · Public-ABI feasibility spike

Implement only the nested table shown in §14.

1. Compile Tier 0 Struct plans.
2. Parse one root object containing one tabular list.
3. Decode row cells directly to final scalar values.
4. Construct nested and outer Structs through class calls.
5. Add debug allocation counters.
6. Implement direct Struct encode for the same shape.
7. Benchmark against wrapper decode and `to_builtins`.

**Exit A:** G2, G3, and G4 pass. Proceed.

**Exit B:** G2 passes but G3 or G4 fails narrowly. Profile constructor calls, attribute reads, plan lookup, and scalar creation; attempt vectorcall and cached descriptor access.

**Exit C:** public-ABI direct construction cannot beat the wrapper. Stop calling the third-party route a solution. Preserve the conformance core and prepare an upstream `msgspec` proposal using the evidence.

### Phase 2 · Untyped 4.1 core

Port the specification as a Rust parser/encoder, not the TypeScript syntax line-for-line.

Implementation order:

1. scanner and position tracking,
2. string/key tokenizer,
3. scalar parser,
4. bracket/header parser,
5. nested field groups,
6. root/object/list forms,
7. tabular arrays,
8. keyed tabular objects,
9. strict validation checklist,
10. canonical writer and number formatting.

After each item, enable the corresponding fixture subset. Never defer all conformance until the end.

**Exit:** all encode, decode, and strict-error fixtures pass for `type=Any`.

### Phase 3 · Typed Tier 0

1. Complete Struct object-form decoding.
2. Complete tabular Struct row decoding.
3. Add lists, optionals, defaults, renames, constraints.
4. Implement unknown-field skipping without materialization.
5. Differential-test against `msgspec.json` for type acceptance and error paths on equivalent values.

**Exit:** challenge-shaped typed path clears G2-G4 and Tier 0 differential tests.

### Phase 4 · Encoder hardening

1. Cache Struct encode plans by exact class.
2. Add mapping and sequence adapters.
3. Complete nested table classifier.
4. Add keyed tabular classification.
5. Complete string quoting and float canonicalization.
6. Add `enc_hook`, Decimal, UUID, and order semantics.

**Exit:** all encode fixtures pass byte-for-byte and direct Struct encoding clears G4.

### Phase 5 · Typed compatibility

Implement Tier 1, then Tier 2. Add each type only with:

- acceptance tests,
- equivalent `msgspec.json` differential tests,
- strict/non-strict tests,
- error path tests,
- benchmark coverage where it could alter hot paths.

### Phase 6 · Packaging and release

1. Build `abi3-py313` wheels for macOS arm64/x86_64, Linux x86_64/aarch64, and Windows x86_64.
2. Install each wheel in a clean environment with only `msgspec` resolved.
3. Run smoke conversion without a compiler.
4. Inspect wheel tags and Python dependency metadata.
5. Run syscall checks proving conversion opens no files, sockets, or subprocesses.
6. Generate the machine-readable conformance and speed report.
7. Attach report and fixture lock to the release.

## 18. CI design

### Pull request CI

- Python lint/type checks.
- `cargo fmt --check` and `cargo clippy --all-targets -- -D warnings`.
- Rust unit tests for scanner/header/scalar/writer.
- Python API and typed vertical-slice tests.
- fixture subset on all platforms.
- full fixture corpus on macOS arm64 and Linux x86_64.
- no benchmark pass/fail on noisy shared runners, but store smoke numbers.

### Release qualification

A dedicated benchmark runner executes:

```text
macOS arm64, release wheel, Python 3.13
```

and optionally a second stable runner on Linux x86_64. The release report names the runner. Performance qualification does not use GitHub-hosted noise as a hard truth source unless repeatability has been demonstrated.

## 19. Risks and explicit stop conditions

### R-01 · Constructor overhead

Calling the Struct class may be materially slower than `msgspec`’s private decoder slot filling. Mitigation: vectorcall, positional fields, cached plans, and row-specialized decoding. Stop condition: G3 still fails after profiling and these optimizations.

### R-02 · Direct field access may miss G4

Stable-ABI attribute access can be expensive. Mitigation: cache interned field names and descriptors, specialize exact Struct classes, and avoid leaf arrays. Stop condition: whole encode remains slower than `to_builtins` alone.

### R-03 · `msgspec.inspect` changes

Mitigation: one adapter module, pinned minimum version, plan-schema golden tests, and CI against the newest compatible msgspec release. No parser code depends on inspection classes.

### R-04 · Full semantics become a clone of msgspec

Mitigation: stage the type ladder and publish the matrix. If the compatibility tail grows without bound, use the result to argue for Route A upstream rather than pretending a third-party clone is cheap to maintain.

### R-05 · Stable ABI costs the speed floor

Mitigation: benchmark the wheel early. Stop condition: a full-ABI build passes but the required `abi3` build cannot. The requirement wins; do not quietly ship version-specific wheels as the qualified result.

### R-06 · Moving TOON target

Mitigation: encode grammar rules in small modules, pin fixtures per release, and make the fixture commit part of the report. A later TOON version is a new qualification target, not an in-place reinterpretation of an old release.

## 20. What this canvas solves and what it does not

### Solved here

- the viable third-party route,
- the no-tree construction mechanism,
- package naming and public API shape,
- stable-ABI boundary,
- parser/consumer separation,
- type-plan compatibility membrane,
- direct Struct encoding strategy,
- nested field-group handling strategy,
- payload-safe errors,
- conformance pinning,
- allocation proof design,
- benchmark gates,
- implementation order,
- stop conditions and upstream fallback.

### Not honestly solved without executing code

- exact fixture pass count,
- exact canonical edge behavior not visible in the fixture corpus yet,
- whether public Struct construction clears the speed requirement,
- whether stable-ABI attribute access clears the encode requirement,
- complete `msgspec` semantic parity,
- wheel success on every target platform.

Those are not “TBD architecture.” They are executable gates with named evidence.

## 21. Recommended first commit sequence

```text
1. chore: scaffold maturin abi3 package and public API
2. test: pin TOON 4.1 fixtures and report schema
3. feat: add zero-copy scanner and payload-safe faults
4. feat: parse headers and nested field groups
5. feat: compile Tier 0 msgspec type plans
6. feat: decode nested tabular rows directly into Structs
7. test: prove no intermediate row dictionaries
8. bench: compare direct typed path with convert wrapper
9. feat: encode Struct rows directly as nested tables
10. bench: compare whole encode with to_builtins alone
11. feat: complete untyped parser against fixture slices
12. feat: complete canonical encoder against fixture slices
13. ci: build and test abi3 wheel matrix
14. release: generate first qualification report
```

## 22. Bottom line

This is worth attempting as a third-party Rust extension because the decisive requirement does not logically require private `msgspec` slot writes. A schema-guided parser can construct final field values and invoke the public Struct constructor without ever building the discarded builtin tree.

That observation turns the problem from “msgspec has no C API, therefore impossible” into a sharper experiment:

> Is public Struct construction plus a native schema-guided TOON parser fast enough to beat the wrapper and clear the specified floors?

The canvas above contains the architecture and vertical slice needed to answer that question. If the answer is yes, the remaining work is disciplined fixture and compatibility engineering. If the answer is no, the project still produces a conforming Rust TOON core and unusually strong evidence that the only qualifying destination is upstream inside `msgspec`.
