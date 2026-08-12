//! PyO3 boundary for msgspec_toon._native.

use std::sync::{Arc, Mutex};

use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyByteArray, PyBytes, PyString};

pub mod containers;
pub mod encode;
pub mod error;
pub mod event;
pub mod header;
pub mod limits;
#[cfg(feature = "experimental-struct-offset-capi")]
mod msgspec_capi;
#[cfg(not(feature = "experimental-struct-offset-capi"))]
mod msgspec_capi {
    use pyo3::prelude::*;

    #[derive(Clone, Copy)]
    pub struct MsgspecCapi;

    impl MsgspecCapi {
        pub fn import(_py: Python<'_>) -> PyResult<Option<Self>> {
            Ok(None)
        }

        pub fn struct_offsets(
            &self,
            _py: Python<'_>,
            _class: &Bound<'_, PyAny>,
        ) -> PyResult<Vec<usize>> {
            unreachable!("experimental Struct-offset C API is not compiled")
        }
    }
}
pub mod parser;
mod plan;
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

/// Opaque, shareable result of lowering a Python `PlanSpec` into the native
/// typed-consumer plan. Python owns the bounded annotation cache; Rust owns
/// the compiled representation (the same split msgspec uses for StructInfo).
#[pyclass(module = "msgspec_toon._native", frozen)]
struct NativePlan {
    inner: Arc<CompiledPlan>,
}

#[pyfunction]
fn compile_plan(py: Python<'_>, spec: &Bound<'_, PyAny>) -> PyResult<NativePlan> {
    Ok(NativePlan {
        inner: Arc::new(CompiledPlan::from_python(py, spec)?),
    })
}

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

#[allow(clippy::too_many_arguments)]
fn decode_typed<const EXTENDED: bool>(
    py: Python<'_>,
    bytes: &[u8],
    plan: &CompiledPlan,
    strict: bool,
    indent_size: usize,
    dec_hook: Option<Py<PyAny>>,
    float_hook: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let mut consumer = TypedConsumer::<EXTENDED>::new(py, plan, strict, dec_hook, float_hook);
    let parsed = if EXTENDED {
        parser::parse_with_object_preflight(bytes, strict, indent_size, &mut consumer)
    } else {
        parser::parse(bytes, strict, indent_size, &mut consumer)
    };
    if let Err(fault) = parsed {
        if let Some(err) = consumer.pending_err.take() {
            return Err(err);
        }
        return Err(fault_to_pyerr(py, &fault));
    }
    consumer
        .take_result()
        .map(Bound::unbind)
        .ok_or_else(|| NativeFault::new_err(("decoder produced no value",)))
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
    extended_plan: bool,
    strict: bool,
    indent_size: usize,
    dec_hook: Option<Py<PyAny>>,
    float_hook: Option<Py<PyAny>>,
}

#[pymethods]
impl Decoder {
    #[new]
    #[pyo3(signature = (*, plan=None, strict=true, indent_size=2, dec_hook=None, float_hook=None))]
    fn new(
        py: Python<'_>,
        plan: Option<Bound<'_, PyAny>>,
        strict: bool,
        indent_size: usize,
        dec_hook: Option<Py<PyAny>>,
        float_hook: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        if indent_size == 0 || indent_size > 16 {
            return Err(PyTypeError::new_err("indent_size must be between 1 and 16"));
        }
        let compiled = match plan.as_ref() {
            Some(spec) => match spec.cast::<NativePlan>() {
                Ok(native) => Some(native.borrow().inner.clone()),
                Err(_) => Some(Arc::new(CompiledPlan::from_python(py, spec)?)),
            },
            None => None,
        };
        let extended_plan = compiled
            .as_ref()
            .is_some_and(|plan| plan.requires_extended_consumer());
        Ok(Self {
            plan: compiled,
            extended_plan,
            strict,
            indent_size,
            dec_hook,
            float_hook,
        })
    }

    fn decode(&self, py: Python<'_>, buf: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let input = extract_input(buf)?;
        let bytes = input.as_bytes()?;

        match &self.plan {
            Some(plan) => {
                let dec_hook = self.dec_hook.as_ref().map(|hook| hook.clone_ref(py));
                let float_hook = self.float_hook.as_ref().map(|hook| hook.clone_ref(py));
                if self.extended_plan {
                    decode_typed::<true>(
                        py,
                        bytes,
                        plan,
                        self.strict,
                        self.indent_size,
                        dec_hook,
                        float_hook,
                    )
                } else {
                    decode_typed::<false>(
                        py,
                        bytes,
                        plan,
                        self.strict,
                        self.indent_size,
                        dec_hook,
                        float_hook,
                    )
                }
            }
            None => {
                let mut consumer = UntypedConsumer::new(
                    py,
                    self.float_hook.as_ref().map(|hook| hook.clone_ref(py)),
                );
                match parser::parse(bytes, self.strict, self.indent_size, &mut consumer) {
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
    // This is the explicit keyword-only PyO3 boundary. Keeping each public
    // option named here preserves inspectable forwarding and avoids an opaque
    // Python dict on every Encoder construction.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (*, enc_hook=None, plan_source, struct_base, encode_error, delimiter=",", indent=2))]
    fn new(
        py: Python<'_>,
        enc_hook: Option<Py<PyAny>>,
        plan_source: Py<PyAny>,
        struct_base: Py<PyAny>,
        encode_error: Py<PyAny>,
        delimiter: &str,
        indent: usize,
    ) -> PyResult<Self> {
        // Only the wire options TOON 4.1 itself defines are accepted.
        let delimiter = match delimiter {
            "," => b',',
            "\t" => b'\t',
            "|" => b'|',
            _ => {
                return Err(PyTypeError::new_err(
                    "delimiter must be \",\", \"\\t\", or \"|\"",
                ));
            }
        };
        if indent == 0 || indent > 16 {
            return Err(PyTypeError::new_err("indent must be between 1 and 16"));
        }
        Ok(Self {
            context: encode::EncodeContext {
                enc_hook,
                struct_base,
                plan_source,
                encode_error,
                struct_api: msgspec_capi::MsgspecCapi::import(py)?,
                cache: Mutex::new(std::collections::HashMap::new()),
                delimiter,
                indent,
            },
        })
    }

    #[getter]
    fn _struct_access(&self) -> &'static str {
        if self.context.struct_api.is_some() {
            "capsule"
        } else {
            "attribute"
        }
    }

    #[getter]
    fn _experimental_struct_offset_capi_enabled(&self) -> bool {
        cfg!(feature = "experimental-struct-offset-capi")
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

/// The G2 evidence surface, present only in an `alloc-stats` build. Absent
/// from the release wheel by construction, so a benchmark can never measure a
/// counter and a report can never read one from an uninstrumented build.
#[cfg(feature = "alloc-stats")]
#[pyfunction]
fn alloc_stats(py: Python<'_>) -> PyResult<Bound<'_, pyo3::types::PyDict>> {
    containers::snapshot_dict(py)
}

#[cfg(feature = "alloc-stats")]
#[pyfunction]
fn reset_alloc_stats() {
    containers::reset();
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativePlan>()?;
    module.add_class::<Decoder>()?;
    module.add_class::<Encoder>()?;
    module.add_function(wrap_pyfunction!(compile_plan, module)?)?;
    module.add("NativeFault", module.py().get_type::<NativeFault>())?;
    #[cfg(feature = "alloc-stats")]
    {
        module.add_function(wrap_pyfunction!(alloc_stats, module)?)?;
        module.add_function(wrap_pyfunction!(reset_alloc_stats, module)?)?;
    }
    Ok(())
}
