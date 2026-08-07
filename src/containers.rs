//! The one place Python containers and Struct instances are created.
//!
//! Two reasons for a single membrane.
//!
//! First, independence of the G2 proof. A counter bolted to the untyped
//! consumer's call sites can only prove that *those call sites* went unused —
//! it says nothing about a container built anywhere else. Every construction
//! in the codec goes through this module instead, and the `disallowed-methods`
//! clippy lint in `clippy.toml` fails the build if `PyDict::new`,
//! `PyList::new`, or `PyTuple::new` is called outside it. A zero is therefore
//! a statement about the codec, not about one consumer.
//!
//! Second, the counters are test-only. Without the `alloc-stats` feature every
//! function below is a bare constructor and the release wheel carries no
//! instrumentation at all, so benchmarks measure codec work and never an
//! atomic increment per output container.
//!
//! The categories are what the *codec* can know, not what a caller intends:
//!
//! ```text
//! builtin_dicts / builtin_lists   built by the untyped builder
//! final_lists / final_dicts       built by the typed consumer for a declared type
//! final_structs                   Struct instances constructed
//! ```
//!
//! An `Any` field asks for a builtin tree, so builtin containers inside an
//! `Any` subtree are requested output, not a G2 violation. G2 is the claim
//! that a decode into a target with no `Any` builds zero builtin containers.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "alloc-stats")]
mod counters {
    use std::sync::atomic::{AtomicU64, Ordering};

    pub static BUILTIN_DICTS: AtomicU64 = AtomicU64::new(0);
    pub static BUILTIN_LISTS: AtomicU64 = AtomicU64::new(0);
    pub static FINAL_LISTS: AtomicU64 = AtomicU64::new(0);
    pub static FINAL_DICTS: AtomicU64 = AtomicU64::new(0);
    pub static FINAL_STRUCTS: AtomicU64 = AtomicU64::new(0);

    pub const ALL: [&AtomicU64; 5] = [
        &BUILTIN_DICTS,
        &BUILTIN_LISTS,
        &FINAL_LISTS,
        &FINAL_DICTS,
        &FINAL_STRUCTS,
    ];

    pub fn bump(counter: &AtomicU64) {
        counter.fetch_add(1, Ordering::Relaxed);
    }

    pub fn snapshot() -> [u64; 5] {
        std::array::from_fn(|index| ALL[index].load(Ordering::Relaxed))
    }

    pub fn reset() {
        for counter in ALL {
            counter.store(0, Ordering::Relaxed);
        }
    }
}

/// The counter names, in `snapshot()` order. Kept beside the statics so the
/// Python-facing report cannot drift from what is actually counted.
#[cfg(feature = "alloc-stats")]
pub const COUNTER_NAMES: [&str; 5] = [
    "builtin_dicts",
    "builtin_lists",
    "final_lists",
    "final_dicts",
    "final_structs",
];

#[cfg(feature = "alloc-stats")]
pub use counters::reset;

/// The probe's own report object. It is the only `PyDict` in the codec that is
/// not codec output, so it is built here — under the same membrane — rather
/// than by exempting a call site elsewhere.
#[cfg(feature = "alloc-stats")]
#[allow(clippy::disallowed_methods)]
pub fn snapshot_dict(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let stats = PyDict::new(py);
    for (name, value) in COUNTER_NAMES.iter().zip(counters::snapshot()) {
        stats.set_item(name, value)?;
    }
    Ok(stats)
}

macro_rules! count {
    ($counter:ident) => {
        #[cfg(feature = "alloc-stats")]
        counters::bump(&counters::$counter);
    };
}

/// A dict in the builtin tree the untyped builder produces.
#[allow(clippy::disallowed_methods)]
pub fn new_builtin_dict(py: Python<'_>) -> Bound<'_, PyDict> {
    count!(BUILTIN_DICTS);
    PyDict::new(py)
}

/// A list in the builtin tree the untyped builder produces.
#[allow(clippy::disallowed_methods)]
pub fn new_builtin_list<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyList>> {
    count!(BUILTIN_LISTS);
    PyList::new(py, items)
}

/// A list the target type declared (`list[T]`).
#[allow(clippy::disallowed_methods)]
pub fn new_final_list<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyList>> {
    count!(FINAL_LISTS);
    PyList::new(py, items)
}

/// A tuple the target type declared (`tuple[T, ...]`). Counted with the final
/// lists: both are the sequence the target asked for.
#[allow(clippy::disallowed_methods)]
pub fn new_final_tuple<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyTuple>> {
    count!(FINAL_LISTS);
    PyTuple::new(py, items)
}

/// A dict the target type declared (`dict[str, T]`).
#[allow(clippy::disallowed_methods)]
pub fn new_final_dict(py: Python<'_>) -> Bound<'_, PyDict> {
    count!(FINAL_DICTS);
    PyDict::new(py)
}

/// Record a Struct instance built by the typed consumer. Construction itself
/// is a vectorcall on the user's class, so only the tally lives here — the
/// count exists so the probe can prove it observed the typed path, rather than
/// reading a zero that would also hold if nothing had been decoded.
pub fn count_struct_instance() {
    count!(FINAL_STRUCTS);
}
