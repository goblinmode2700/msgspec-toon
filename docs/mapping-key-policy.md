# Mapping key policy

`msgspec-toon` supports `dict[str, T]`. It rejects `dict[int, T]` and all other non-string
mapping-key annotations when it constructs the decoder.

TOON object keys are text. A non-string target needs a second conversion step before insertion.
That step also needs collision rules. For example, permissive integer conversion can make `"1"`
and another numeric spelling refer to the same Python key. The current direct mapping frame has no
proven collision policy that matches `msgspec.json` in strict and permissive modes.

The repository and pinned TOON corpus contain no required non-string mapping-key payload. The
executable support matrix has one explicit probe for this boundary. Therefore, the current release
keeps the plan-construction rejection. It returns `TypePlanError` with code
`unsupported_mapping_key` and a schema-only path. It does not decode to the wrong key type.

Untyped encoding also rejects mappings with non-string keys instead of silently choosing a
stringification and collision policy. Its `EncodeError` names
`msgspec.to_builtins(value, str_keys=True)` as the supported explicit conversion route for callers
that choose msgspec's policy.

This decision can change only after differential tests define conversion, collision, large-integer,
and payload-safety behavior.
