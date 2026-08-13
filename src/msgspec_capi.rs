//! Optional msgspec cross-extension C API.
//!
//! The capsule is absent in msgspec 0.21.1, so absence is a supported fallback.
//! A present but incompatible capsule is an installation error and fails loudly.

use std::ffi::c_int;
use std::mem::size_of;
use std::ptr;

use pyo3::exceptions::{PyAttributeError, PyImportError, PySystemError};
use pyo3::ffi;
use pyo3::prelude::*;

const CAPSULE_NAME: &std::ffi::CStr = c"msgspec._core._C_API";
const ABI_VERSION: u32 = 1;
const MAX_STRUCT_FIELDS: usize = 4096;

type StructOffsetsFn = unsafe extern "C" fn(
    class: *mut ffi::PyObject,
    offsets: *mut *const isize,
    nfields: *mut isize,
) -> c_int;

#[repr(C)]
struct RawMsgspecCapi {
    abi_version: u32,
    struct_size: u32,
    struct_offsets: Option<StructOffsetsFn>,
}

#[derive(Clone, Copy)]
pub struct MsgspecCapi {
    struct_offsets: StructOffsetsFn,
}

impl MsgspecCapi {
    pub fn import(py: Python<'_>) -> PyResult<Option<Self>> {
        let core = py.import("msgspec._core")?;
        let capsule = match core.getattr("_C_API") {
            Ok(capsule) => capsule,
            Err(err) if err.is_instance_of::<PyAttributeError>(py) => return Ok(None),
            Err(err) => return Err(err),
        };
        // SAFETY: `capsule` is a live Python reference for this call. CPython
        // validates the exact capsule name and returns null with an exception
        // on a type/name mismatch. A non-null table pointer is guaranteed by
        // the producer's named-capsule ABI to remain valid for module life.
        let raw = unsafe { ffi::PyCapsule_GetPointer(capsule.as_ptr(), CAPSULE_NAME.as_ptr()) };
        if raw.is_null() {
            return Err(PyErr::fetch(py));
        }
        // SAFETY: the named-capsule producer contract above supplies at least
        // the fixed header. `validate_table` checks its version and byte size
        // before any optional function is called.
        let table = unsafe { &*raw.cast::<RawMsgspecCapi>() };
        let struct_offsets = validate_table(table)?;
        Ok(Some(Self { struct_offsets }))
    }

    pub fn struct_offsets(&self, py: Python<'_>, class: &Bound<'_, PyAny>) -> PyResult<Vec<usize>> {
        let mut offsets = ptr::null();
        let mut nfields = 0isize;
        // SAFETY: `class` is strongly held for this call. The validated ABI
        // function writes only the two out-parameters and returns a
        // class-owned immutable view that remains live while the class lives.
        let status = unsafe { (self.struct_offsets)(class.as_ptr(), &mut offsets, &mut nfields) };
        if status < 0 {
            return Err(PyErr::fetch(py));
        }
        // SAFETY: success transfers a borrowed view with the ABI lifetime
        // stated above. This helper validates count and nullability before it
        // creates a slice, and copies every offset before returning.
        unsafe { copy_offset_view(offsets, nfields) }
    }
}

fn validate_table(table: &RawMsgspecCapi) -> PyResult<StructOffsetsFn> {
    validate_header(table.abi_version, table.struct_size)?;
    table
        .struct_offsets
        .ok_or_else(|| PyImportError::new_err("msgspec C API has no Struct-offset function"))
}

/// Copy a producer-owned offset view after validating every slice precondition.
///
/// # Safety
///
/// For `nfields > 0`, `offsets` must point to `nfields` initialized `isize`
/// values that remain readable for this call. The named capsule ABI is the
/// only production caller that can provide this lifetime.
unsafe fn copy_offset_view(offsets: *const isize, nfields: isize) -> PyResult<Vec<usize>> {
    let count = usize::try_from(nfields).map_err(|_| {
        PySystemError::new_err("msgspec C API returned a negative Struct field count")
    })?;
    if count > MAX_STRUCT_FIELDS || (count > 0 && offsets.is_null()) {
        return Err(PySystemError::new_err(
            "msgspec C API returned an invalid Struct-offset view",
        ));
    }
    // SAFETY: the caller supplies a readable view; the checks above establish
    // non-null (unless empty) and a bounded element count.
    let raw = unsafe { std::slice::from_raw_parts(offsets, count) };
    raw.iter()
        .map(|offset| {
            usize::try_from(*offset).map_err(|_| {
                PySystemError::new_err("msgspec C API returned a negative field offset")
            })
        })
        .collect()
}

fn validate_header(abi_version: u32, struct_size: u32) -> PyResult<()> {
    if abi_version != ABI_VERSION {
        return Err(PyImportError::new_err(format!(
            "unsupported msgspec C API version {abi_version}; expected {ABI_VERSION}",
        )));
    }
    if (struct_size as usize) < size_of::<RawMsgspecCapi>() {
        return Err(PyImportError::new_err(format!(
            "msgspec C API table is {struct_size} bytes; expected at least {}",
            size_of::<RawMsgspecCapi>(),
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_wrong_abi_version() {
        Python::initialize();
        Python::attach(|py| {
            let err =
                validate_header(ABI_VERSION + 1, size_of::<RawMsgspecCapi>() as u32).unwrap_err();
            assert!(err.is_instance_of::<PyImportError>(py));
        });
    }

    #[test]
    fn rejects_short_table() {
        Python::initialize();
        Python::attach(|py| {
            let err = validate_header(ABI_VERSION, 4).unwrap_err();
            assert!(err.is_instance_of::<PyImportError>(py));
        });
    }

    #[test]
    fn rejects_missing_function_and_invalid_offset_views() {
        Python::initialize();
        Python::attach(|py| {
            let table = RawMsgspecCapi {
                abi_version: ABI_VERSION,
                struct_size: size_of::<RawMsgspecCapi>() as u32,
                struct_offsets: None,
            };
            assert!(
                validate_table(&table)
                    .unwrap_err()
                    .is_instance_of::<PyImportError>(py)
            );

            assert!(
                unsafe { copy_offset_view(ptr::null(), 1) }
                    .unwrap_err()
                    .is_instance_of::<PySystemError>(py)
            );
            assert!(
                unsafe { copy_offset_view(ptr::null(), -1) }
                    .unwrap_err()
                    .is_instance_of::<PySystemError>(py)
            );
            assert!(
                unsafe { copy_offset_view(ptr::null(), MAX_STRUCT_FIELDS as isize + 1) }
                    .unwrap_err()
                    .is_instance_of::<PySystemError>(py)
            );

            let offsets = [8isize, -1];
            assert!(
                unsafe { copy_offset_view(offsets.as_ptr(), offsets.len() as isize) }
                    .unwrap_err()
                    .is_instance_of::<PySystemError>(py)
            );
        });
    }
}
