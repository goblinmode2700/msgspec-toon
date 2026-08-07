//! PyO3 boundary for msgspec_toon._native.

use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};

use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyByteArray, PyBytes, PyString};

pub mod encode;
pub mod error;
pub mod event;
pub mod header;
pub mod parser;
pub mod plan;
pub mod pyval;
pub mod scalar;
pub mod scan;
pub mod typed;
pub mod untyped;
pub mod writer;

use error::Fault;
use plan::CompiledPlan;
use typed::TypedConsumer;
use untyped::UntypedConsumer;

create_exception!(_native, NativeFault, PyException);

fn fault_to_pyerr(py: Python<'_>, fault: &Fault) -> PyErr {
    let err = NativeFault::new_err((fault.safe_message(),));
    let value = err.value(py);
    let _ = value.setattr("safe_message", fault.safe_message());
    let _ = value.setattr("code", fault.code.as_str());
    let _ = value.setattr("line", fault.line);
    let _ = value.setattr("column", fault.column);
    let _ = value.setattr("validation", fault.validation);
    err
}

enum InputView<'py> {
    Borrowed(Bound<'py, PyAny>),
    Owned(Vec<u8>),
}

impl InputView<'_> {
    fn as_bytes(&self) -> PyResult<&[u8]> {
        match self {
            Self::Borrowed(obj) => {
                if let Ok(bytes) = obj.cast::<PyBytes>() {
                    Ok(bytes.as_bytes())
                } else if let Ok(text) = obj.cast::<PyString>() {
                    Ok(text.to_str()?.as_bytes())
                } else {
                    Err(PyTypeError::new_err("unreachable input view"))
                }
            }
            Self::Owned(bytes) => Ok(bytes),
        }
    }
}

fn extract_input<'py>(buf: &Bound<'py, PyAny>) -> PyResult<InputView<'py>> {
    if buf.cast::<PyBytes>().is_ok() || buf.cast::<PyString>().is_ok() {
        return Ok(InputView::Borrowed(buf.clone()));
    }
    if let Ok(array) = buf.cast::<PyByteArray>() {
        return Ok(InputView::Owned(array.to_vec()));
    }
    // memoryview and other buffer-protocol objects.
    if let Ok(raw) = buf.call_method0("tobytes")
        && let Ok(bytes) = raw.cast::<PyBytes>()
    {
        return Ok(InputView::Owned(bytes.as_bytes().to_vec()));
    }
    Err(PyTypeError::new_err(
        "decode input must be bytes, bytearray, memoryview, or str",
    ))
}

#[pyclass(module = "msgspec_toon._native")]
struct Decoder {
    plan: Option<Arc<CompiledPlan>>,
    strict: bool,
    dec_hook: Option<Py<PyAny>>,
    float_hook: Option<Py<PyAny>>,
}

#[pymethods]
impl Decoder {
    #[new]
    #[pyo3(signature = (*, plan=None, strict=true, dec_hook=None, float_hook=None))]
    fn new(
        py: Python<'_>,
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
            strict,
            dec_hook,
            float_hook,
        })
    }

    fn decode(&self, py: Python<'_>, buf: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let input = extract_input(buf)?;
        let bytes = input.as_bytes()?;

        match &self.plan {
            Some(plan) => {
                let mut consumer = TypedConsumer::new(
                    py,
                    plan,
                    self.strict,
                    self.dec_hook.as_ref().map(|hook| hook.clone_ref(py)),
                    self.float_hook.as_ref().map(|hook| hook.clone_ref(py)),
                );
                match parser::parse(bytes, self.strict, &mut consumer) {
                    Ok(()) => {}
                    Err(fault) => {
                        if let Some(err) = consumer.pending_err.take() {
                            return Err(err);
                        }
                        return Err(fault_to_pyerr(py, &fault));
                    }
                }
                consumer
                    .take_result()
                    .map(Bound::unbind)
                    .ok_or_else(|| NativeFault::new_err(("decoder produced no value",)))
            }
            None => {
                let mut consumer = UntypedConsumer::new(
                    py,
                    self.float_hook.as_ref().map(|hook| hook.clone_ref(py)),
                );
                match parser::parse(bytes, self.strict, &mut consumer) {
                    Ok(()) => {}
                    Err(fault) => {
                        if let Some(err) = consumer.pending_err.take() {
                            return Err(err);
                        }
                        return Err(fault_to_pyerr(py, &fault));
                    }
                }
                consumer
                    .take_result()
                    .map(Bound::unbind)
                    .ok_or_else(|| NativeFault::new_err(("decoder produced no value",)))
            }
        }
    }
}

#[pyclass(module = "msgspec_toon._native")]
struct Encoder {
    context: encode::EncodeContext,
}

#[pymethods]
impl Encoder {
    #[new]
    #[pyo3(signature = (*, enc_hook=None, plan_source, struct_base, encode_error))]
    fn new(
        enc_hook: Option<Py<PyAny>>,
        plan_source: Py<PyAny>,
        struct_base: Py<PyAny>,
        encode_error: Py<PyAny>,
    ) -> Self {
        Self {
            context: encode::EncodeContext {
                enc_hook,
                struct_base,
                plan_source,
                encode_error,
                cache: Mutex::new(std::collections::HashMap::new()),
            },
        }
    }

    fn encode<'py>(
        &self,
        py: Python<'py>,
        obj: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let out = encode::encode_root(&self.context, py, obj)?;
        Ok(PyBytes::new(py, &out))
    }
}

/// Intermediate builtin-container allocation counters (the G2 evidence).
#[pyfunction]
fn alloc_stats() -> (u64, u64) {
    (
        pyval::INTERMEDIATE_DICTS.load(Ordering::Relaxed),
        pyval::INTERMEDIATE_LISTS.load(Ordering::Relaxed),
    )
}

#[pyfunction]
fn reset_alloc_stats() {
    pyval::INTERMEDIATE_DICTS.store(0, Ordering::Relaxed);
    pyval::INTERMEDIATE_LISTS.store(0, Ordering::Relaxed);
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Decoder>()?;
    module.add_class::<Encoder>()?;
    module.add("NativeFault", module.py().get_type::<NativeFault>())?;
    module.add_function(wrap_pyfunction!(alloc_stats, module)?)?;
    module.add_function(wrap_pyfunction!(reset_alloc_stats, module)?)?;
    Ok(())
}
