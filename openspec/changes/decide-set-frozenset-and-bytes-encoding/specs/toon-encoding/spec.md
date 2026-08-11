## ADDED Requirements

### Requirement: Set-like values and bytes have explicit encode policies

The release SHALL declare `set`, `frozenset`, and `bytes` as natively supported or intentionally
rejected. Native bytes support SHALL use the base64 value produced by `msgspec==0.21.1` and SHALL
write that value as a TOON string.

Native set-like support SHALL produce the same canonical bytes across supported processes and
platforms. If the encoder cannot define that order for all supported elements, it SHALL reject the
type before output.

#### Scenario: Bytes policy is executable

- **WHEN** the encoder receives `b"ab"`
- **THEN** it writes the declared base64 TOON string or raises the declared refusal
- **AND** the support matrix matches the observed result

#### Scenario: Set-like output is stable or refused

- **WHEN** equivalent set-like values are created with different insertion and process orders
- **THEN** native support writes identical bytes or every call raises the declared refusal
- **AND** no release claims canonical support from one process order

