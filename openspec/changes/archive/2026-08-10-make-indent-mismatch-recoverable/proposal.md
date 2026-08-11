## Why

`encode(..., indent=1)` produces valid TOON that the default width-two decoder rejects, while
the current error does not reveal the observed width needed to repair the call. Because the
indentation unit is absent from the wire, a recoverable diagnostic is required beside the
documented token-saving option.

## What Changes

- Report the observed leading-space count and the `indent_size` recovery action when strict
  decode sees a nonmultiple indentation.
- Preserve the TOON default of two and require nondefault producer/consumer widths to agree.
- Cover nested mappings and tables at widths 1, 2, and 4 through functional, reusable, typed,
  and untyped decoders.
- Document the out-of-band option contract and existing UTF-8 BOM acceptance.
- Record and reject automatic inference because its exact-source decode A/B gate regressed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `toon-parsing`: invalid-indentation coordinates and text make the observed width recoverable.
- `public-api`: documentation and errors state the producer/consumer indentation contract.
- `distribution-quality`: release evidence covers the width matrix and the rejected inference
  candidate.

## Impact

The adopted code change is confined to the scanner's invalid-indentation branch and static error
formatting from its permitted coordinate. Tests, README, changelog, generated evidence, and beta
metadata also change. There is no successful-path parser, dependency, API signature, or wire-byte
change.
