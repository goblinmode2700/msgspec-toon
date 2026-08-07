//! Containment limits for payload-chosen quantities.
//!
//! Every bound in this module exists because the *input*, not the program,
//! picks the number it constrains. Nesting depth drives recursion; a declared
//! array count drives an allocation hint. Both arrive from an untrusted
//! document, so both need a ceiling before they reach a stack or an allocator.
//! Exceeding a limit is a codec fault with static text (AD-007), never a
//! panic, an abort, or a signal.

/// One nesting ceiling shared by line indentation, header field groups,
/// encoder writing, and encoder shape discovery. Real TOON documents nest
/// far below it; the limit exists to turn a hostile document into a fault
/// instead of a stack overflow.
pub const MAX_NESTING_DEPTH: usize = 256;

/// Element slots a declared array count may reserve up front.
///
/// A declared count is a claim, not a measurement: `[18446744073709551615]:`
/// is three dozen bytes and asks for every address in the machine. The
/// reservation is only an optimization — it saves `log2(n)` growth
/// reallocations while rows stream in — so capping it costs a handful of
/// doublings on arrays larger than the cap and nothing at all below it. At
/// one pointer per slot the worst-case up-front reservation is 512 KiB.
const MAX_RESERVED_ELEMENTS: usize = 1 << 16;

/// Output bytes a row-count estimate may reserve up front. Same reasoning as
/// [`MAX_RESERVED_ELEMENTS`], applied to the encoder's tabular-block estimate,
/// which multiplies a real row count by a per-row width guess.
const MAX_RESERVED_BYTES: usize = 1 << 26;

/// Clamp a declared array count to a reservation hint. The parser keeps the
/// full declared count for count validation; only the allocation is capped.
pub fn reserve_elements(declared_len: usize) -> usize {
    declared_len.min(MAX_RESERVED_ELEMENTS)
}

/// Clamp an output-size estimate to a reservation hint.
pub fn reserve_bytes(estimate: usize) -> usize {
    estimate.min(MAX_RESERVED_BYTES)
}
