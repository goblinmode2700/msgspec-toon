## Context

See `proposal.md` for motivation. TOON treats indentation width as an encoder/decoder option and
does not declare it on the wire. The pinned corpus proves that automatic interpretation is
ambiguous: four leading spaces can be one level at width four or an invalid two-level jump at
width two.

An automatic-discovery candidate distinguished omitted from explicit configuration and inferred
once during scanning. It passed correctness but reproduced a typed-decode slowdown against the
exact preceding source. C9 therefore rejects it even though a same-binary automatic/explicit
comparison was neutral.

## Goals / Non-Goals

**Goals:**

- Make a width mismatch correctable from the exception without payload text.
- Preserve the specification default, strict fixture behavior, and successful decode hot path.
- Apply the diagnostic to typed/untyped and functional/reusable decode through their shared scan.

**Non-Goals:**

- Infer indentation, retry parsing, or add indentation metadata to canonical TOON.
- Change `strict=False` leniency.
- Reopen codec optimization.

## Decisions

1. **Use the report's recoverable-error option.** Default `indent_size=2` remains unchanged.
   Nondefault encoders require the decoder to receive the same value.
2. **Enrich only the caught Python exception.** The Rust parser and native extension source remain
   byte-identical to the preceding checkpoint. After a structural indentation fault, the Python
   veneer scans to the native line coordinate, counts only leading spaces, and discards the view.
   It never retains or formats a source line, token, key, or value. The public column becomes the
   first content column and the count is therefore a coordinate rendered in useful form.
3. **Keep the successful path byte-for-byte shaped.** Successful native decode executes unchanged.
   The buffer scan and dynamic formatting exist only after the native decoder has already failed.
4. **Reject inference from the product, retain its evidence privately.** Functional decode was
   neutral, but typed decode at 46 records reproduced slower. The alternative cannot ship under
   C9 while its cause is unknown.

## Risks / Trade-offs

- **The option still travels out of band.** -> README states this directly beside `indent=1` token
  guidance; the exception supplies the observed setting after a mismatch.
- **A line's raw indentation can be a multiple of the true unit.** -> The diagnostic reports the
  observed line indentation, not a claimed document-wide inferred unit. It tells the caller what
  was observed and preserves strict override semantics.
- **The error message becomes dynamic.** -> Its only new dynamic value is a structural coordinate:
  the leading-space count. Payload text and scalar/key values remain absent; sentinel and
  all-buffer-type tests stay authoritative.

## Migration Plan

Ship in the next beta patch serial. No code migration is required. Pipelines using nondefault
indentation should continue to pass the same integer to encode and decode.
