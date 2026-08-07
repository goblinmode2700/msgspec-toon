//! Scalar tokens to final Python values, and the allocation counters used by
//! the no-intermediate-tree proof (requirements G2).

use std::sync::atomic::{AtomicU64, Ordering};

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyString};

use crate::event::ScalarToken;
use crate::scalar::unescape;

/// Builtin containers created while decoding into a *discardable* tree.
/// The typed consumer never increments these; the untyped consumer counts
/// every dict/list it builds. Final containers requested by the target type
/// (e.g. a `list[Worker]`) are not intermediate and are not counted.
pub static INTERMEDIATE_DICTS: AtomicU64 = AtomicU64::new(0);
pub static INTERMEDIATE_LISTS: AtomicU64 = AtomicU64::new(0);

pub fn count_dict() {
    INTERMEDIATE_DICTS.fetch_add(1, Ordering::Relaxed);
}

pub fn count_list() {
    INTERMEDIATE_LISTS.fetch_add(1, Ordering::Relaxed);
}

pub fn int_from_digits<'py>(py: Python<'py>, digits: &[u8]) -> PyResult<Bound<'py, PyAny>> {
    // The token is validated ASCII digits (with optional sign).
    let text = unsafe { std::str::from_utf8_unchecked(digits) };
    if let Ok(small) = text.parse::<i64>() {
        return Ok(small.into_pyobject(py)?.into_any());
    }
    // Arbitrary precision: hand the decimal digits to CPython directly.
    let c_text = std::ffi::CString::new(digits).expect("digit token has no NUL");
    unsafe {
        let raw = pyo3::ffi::PyLong_FromString(c_text.as_ptr(), std::ptr::null_mut(), 10);
        Bound::from_owned_ptr_or_err(py, raw)
    }
}

pub fn float_from_digits<'py>(
    py: Python<'py>,
    digits: &[u8],
    float_hook: Option<&Py<PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let text = unsafe { std::str::from_utf8_unchecked(digits) };
    if let Some(hook) = float_hook {
        return hook.bind(py).call1((text,));
    }
    let value: f64 = text.parse().map_err(|_| {
        pyo3::exceptions::PyValueError::new_err("unparseable float token")
    })?;
    Ok(value.into_pyobject(py)?.into_any())
}

pub fn string_token_to_py<'py>(
    py: Python<'py>,
    inner: &[u8],
    escaped: bool,
) -> Bound<'py, PyAny> {
    let bytes = unescape(inner, escaped);
    // The document was validated as UTF-8 and escapes decode to valid UTF-8.
    let text = unsafe { std::str::from_utf8_unchecked(&bytes) };
    PyString::new(py, text).into_any()
}

/// The untyped conversion: exactly the Python value TOON declares.
pub fn scalar_to_py<'py>(
    py: Python<'py>,
    token: ScalarToken<'_>,
    float_hook: Option<&Py<PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    match token {
        ScalarToken::Null => Ok(py.None().into_bound(py)),
        ScalarToken::Bool(value) => Ok(PyBool::new(py, value).to_owned().into_any()),
        ScalarToken::Integer(digits) => int_from_digits(py, digits),
        ScalarToken::Float(digits) => float_from_digits(py, digits, float_hook),
        ScalarToken::BareString(bytes) => Ok(string_token_to_py(py, bytes, false)),
        ScalarToken::Quoted { inner, escaped } => Ok(string_token_to_py(py, inner, escaped)),
    }
}
