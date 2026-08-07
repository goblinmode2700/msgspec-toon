//! The typed consumer: constructs the requested target directly from parser
//! events (canvas AD-001, §9).
//!
//! Invariant: for a Struct target the frame stores one optional final value
//! per declared field — a constructor argument frame — never a mapping from
//! wire keys to values. No discardable dict/list tree exists at any point.

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyList, PyTuple};

use crate::error::{Fault, FaultCode, Position};
use crate::event::{Consumer, ScalarToken, StringToken};
use crate::plan::{CompiledPlan, DefaultPlan, PlanKind, StructPlan};
use crate::pyval::{float_from_digits, int_from_digits, scalar_to_py, string_token_to_py};
use crate::scalar::unescape;
use crate::untyped::UntypedConsumer;

enum Frame<'py, 'plan> {
    Struct {
        plan: &'plan StructPlan,
        values: Vec<Option<Bound<'py, PyAny>>>,
        awaiting: Option<usize>,
        skip_value: bool,
    },
    List {
        items: Vec<Bound<'py, PyAny>>,
        item: &'plan CompiledPlan,
        as_tuple: bool,
    },
    Dict {
        map: Bound<'py, PyDict>,
        pending: Option<Bound<'py, PyAny>>,
        value: &'plan CompiledPlan,
    },
}

/// Optimization D1: rows of one array repeat an identical key-event
/// sequence, so the first row's wire-name→field-index resolutions are
/// recorded and replayed positionally for every later row — a byte
/// comparison instead of a hash lookup per cell. Any sequence deviation
/// disables the memo for that array and falls back to hashing.
#[derive(Default)]
struct RowMemo {
    entries: Vec<(Vec<u8>, Option<usize>)>,
    cursor: usize,
    complete: bool,
    disabled: bool,
}

pub struct TypedConsumer<'py, 'plan> {
    py: Python<'py>,
    root: &'plan CompiledPlan,
    strict: bool,
    dec_hook: Option<Py<PyAny>>,
    float_hook: Option<Py<PyAny>>,
    stack: Vec<Frame<'py, 'plan>>,
    result: Option<Bound<'py, PyAny>>,
    pub pending_err: Option<PyErr>,
    skip_depth: usize,
    any_sub: Option<(UntypedConsumer<'py>, usize)>,
    any_hook_class: Option<Py<PyAny>>,
    /// Recycled per-row constructor frames: rows of a tabular array reuse
    /// the same field-slot and argument buffers instead of allocating.
    values_pool: Vec<Vec<Option<Bound<'py, PyAny>>>>,
    arguments_scratch: Vec<Bound<'py, PyAny>>,
    /// One memo per open array frame, scoped like the frame stack.
    row_memos: Vec<RowMemo>,
}

impl<'py, 'plan> TypedConsumer<'py, 'plan> {
    pub fn new(
        py: Python<'py>,
        root: &'plan CompiledPlan,
        strict: bool,
        dec_hook: Option<Py<PyAny>>,
        float_hook: Option<Py<PyAny>>,
    ) -> Self {
        Self {
            py,
            root,
            strict,
            dec_hook,
            float_hook,
            stack: Vec::new(),
            result: None,
            pending_err: None,
            skip_depth: 0,
            any_sub: None,
            any_hook_class: None,
            values_pool: Vec::new(),
            arguments_scratch: Vec::new(),
            row_memos: Vec::new(),
        }
    }

    pub fn take_result(&mut self) -> Option<Bound<'py, PyAny>> {
        self.result.take()
    }

    fn internal(&mut self, err: PyErr, at: Position) -> Fault {
        self.pending_err = Some(err);
        Fault::syntax_at(FaultCode::Internal, at)
    }

    fn expected_plan(&self) -> Option<&'plan CompiledPlan> {
        match self.stack.last() {
            Some(Frame::Struct {
                plan,
                awaiting: Some(index),
                ..
            }) => Some(&plan.fields[*index].value),
            Some(Frame::Struct { .. }) => None,
            Some(Frame::List { item, .. }) => Some(item),
            Some(Frame::Dict { value, .. }) => Some(value),
            None => Some(self.root),
        }
    }

    fn place(&mut self, value: Bound<'py, PyAny>, at: Position) -> Result<(), Fault> {
        match self.stack.last_mut() {
            Some(Frame::Struct {
                values, awaiting, ..
            }) => {
                let index = awaiting
                    .take()
                    .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
                values[index] = Some(value);
            }
            Some(Frame::List { items, .. }) => items.push(value),
            Some(Frame::Dict { map, pending, .. }) => {
                let key = pending
                    .take()
                    .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
                if let Err(err) = map.set_item(key, value) {
                    return Err(self.internal(err, at));
                }
            }
            None => self.result = Some(value),
        }
        Ok(())
    }

    fn convert_scalar(
        &mut self,
        plan: &'plan CompiledPlan,
        token: ScalarToken<'_>,
        at: Position,
    ) -> Result<Bound<'py, PyAny>, Fault> {
        let py = self.py;
        match &plan.kind {
            PlanKind::Any => {
                let converted = scalar_to_py(py, token, self.float_hook.as_ref());
                converted.map_err(|err| self.internal(err, at))
            }
            PlanKind::NoneT => match token {
                ScalarToken::Null => Ok(py.None().into_bound(py)),
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Bool => match token {
                ScalarToken::Bool(value) => Ok(PyBool::new(py, value).to_owned().into_any()),
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Int => match token {
                ScalarToken::Integer(digits) => {
                    int_from_digits(py, digits).map_err(|err| self.internal(err, at))
                }
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Float => match token {
                ScalarToken::Integer(digits) | ScalarToken::Float(digits) => {
                    float_from_digits(py, digits, self.float_hook.as_ref())
                        .map_err(|err| self.internal(err, at))
                }
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Str => match token {
                ScalarToken::BareString(bytes) => Ok(string_token_to_py(py, bytes, false)),
                ScalarToken::Quoted { inner, escaped } => {
                    Ok(string_token_to_py(py, inner, escaped))
                }
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Union(union) => {
                if matches!(token, ScalarToken::Null) {
                    return if union.nullable {
                        Ok(py.None().into_bound(py))
                    } else {
                        Err(Fault::validation_at(FaultCode::TypeMismatch, at))
                    };
                }
                for member in &union.members {
                    match self.convert_scalar(member, token, at) {
                        Ok(value) => return Ok(value),
                        Err(fault) if fault.code == FaultCode::TypeMismatch => continue,
                        Err(fault) => return Err(fault),
                    }
                }
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            PlanKind::Literal(values) => {
                let converted = scalar_to_py(py, token, self.float_hook.as_ref());
                let value = match converted {
                    Ok(value) => value,
                    Err(err) => return Err(self.internal(err, at)),
                };
                for candidate in values {
                    match value.eq(candidate.bind(py)) {
                        Ok(true) => return Ok(value),
                        Ok(false) => {}
                        Err(err) => return Err(self.internal(err, at)),
                    }
                }
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            PlanKind::Custom(class) => {
                let Some(hook) = self.dec_hook.as_ref() else {
                    return Err(Fault::validation_at(FaultCode::UnsupportedType, at));
                };
                let raw = match scalar_to_py(py, token, self.float_hook.as_ref()) {
                    Ok(value) => value,
                    Err(err) => return Err(self.internal(err, at)),
                };
                let hook = hook.clone_ref(py);
                let class = class.clone_ref(py);
                hook.bind(py)
                    .call1((class, raw))
                    .map_err(|err| self.internal(err, at))
            }
            PlanKind::List(_)
            | PlanKind::TupleVar(_)
            | PlanKind::Dict(_, _)
            | PlanKind::Struct(_) => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
        }
    }

    fn finish_struct(
        &mut self,
        plan: &'plan StructPlan,
        mut values: Vec<Option<Bound<'py, PyAny>>>,
        at: Position,
    ) -> Result<Bound<'py, PyAny>, Fault> {
        let py = self.py;
        let mut arguments = std::mem::take(&mut self.arguments_scratch);
        arguments.clear();
        for (index, field) in plan.fields.iter().enumerate() {
            let value = match values[index].take() {
                Some(value) => value,
                None => match &field.default {
                    DefaultPlan::Required => {
                        return Err(Fault::validation_at(FaultCode::MissingField, at));
                    }
                    DefaultPlan::Value(default) => default.bind(py).clone(),
                    DefaultPlan::Factory(factory) => {
                        let factory = factory.clone_ref(py);
                        match factory.bind(py).call0() {
                            Ok(value) => value,
                            Err(err) => return Err(self.internal(err, at)),
                        }
                    }
                },
            };
            arguments.push(value);
        }
        values.clear();
        self.values_pool.push(values);
        // Vectorcall the Struct class: no argument tuple per constructed row.
        let pointers: smallvec::SmallVec<[*mut pyo3::ffi::PyObject; 16]> =
            arguments.iter().map(|argument| argument.as_ptr()).collect();
        let raw = unsafe {
            pyo3::ffi::PyObject_Vectorcall(
                plan.class.as_ptr(),
                pointers.as_ptr(),
                pointers.len(),
                std::ptr::null_mut(),
            )
        };
        arguments.clear();
        self.arguments_scratch = arguments;
        unsafe { Bound::from_owned_ptr_or_err(py, raw) }.map_err(|err| self.internal(err, at))
    }

    /// Route an event into the untyped sub-consumer while inside an `Any`
    /// subtree; returns true when the event was consumed.
    fn any_forward(&mut self, event: AnyEvent<'_>, at: Position) -> Result<bool, Fault> {
        let Some((sub, depth)) = self.any_sub.as_mut() else {
            return Ok(false);
        };
        let outcome = match event {
            AnyEvent::StartObject => {
                *depth += 1;
                sub.start_object(at)
            }
            AnyEvent::StartArray(len) => {
                *depth += 1;
                sub.start_array(len, at)
            }
            AnyEvent::Key(key) => sub.key(key, at),
            AnyEvent::Scalar(token) => sub.scalar(token, at),
            AnyEvent::EndObject => {
                *depth -= 1;
                sub.end_object(at)
            }
            AnyEvent::EndArray => {
                *depth -= 1;
                sub.end_array(at)
            }
        };
        if let Err(fault) = outcome {
            if let Some((sub, _)) = self.any_sub.as_mut()
                && let Some(err) = sub.pending_err.take()
            {
                self.pending_err = Some(err);
            }
            return Err(fault);
        }
        let finished = self.any_sub.as_ref().is_some_and(|(_, depth)| *depth == 0);
        if finished {
            let (mut sub, _) = self.any_sub.take().unwrap();
            let value = sub
                .take_result()
                .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
            let value = match self.any_hook_class.take() {
                Some(class) => {
                    let hook = self
                        .dec_hook
                        .as_ref()
                        .expect("any_hook_class only set with dec_hook")
                        .clone_ref(self.py);
                    match hook.bind(self.py).call1((class, value)) {
                        Ok(value) => value,
                        Err(err) => return Err(self.internal(err, at)),
                    }
                }
                None => value,
            };
            self.place(value, at)?;
        }
        Ok(true)
    }

    fn begin_any(
        &mut self,
        event: AnyEvent<'_>,
        at: Position,
        hook_class: Option<Py<PyAny>>,
    ) -> Result<(), Fault> {
        let float_hook = self.float_hook.as_ref().map(|hook| hook.clone_ref(self.py));
        let sub = UntypedConsumer::new(self.py, float_hook);
        self.any_sub = Some((sub, 0));
        self.any_hook_class = hook_class;
        self.any_forward(event, at)?;
        Ok(())
    }

    fn top_struct_skips(&mut self) -> bool {
        matches!(
            self.stack.last(),
            Some(Frame::Struct {
                skip_value: true,
                ..
            })
        )
    }

    fn clear_top_skip(&mut self) {
        if let Some(Frame::Struct { skip_value, .. }) = self.stack.last_mut() {
            *skip_value = false;
        }
    }
}

enum AnyEvent<'a> {
    StartObject,
    EndObject,
    StartArray(usize),
    EndArray,
    Key(StringToken<'a>),
    Scalar(ScalarToken<'a>),
}

impl Consumer for TypedConsumer<'_, '_> {
    fn start_object(&mut self, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::StartObject, at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            self.skip_depth += 1;
            return Ok(());
        }
        if self.top_struct_skips() {
            self.skip_depth = 1;
            return Ok(());
        }
        let expected = self
            .expected_plan()
            .ok_or(Fault::syntax_at(FaultCode::Internal, at))?
            .resolve_container();
        match &expected.kind {
            PlanKind::Struct(plan) => {
                // A struct opening directly under an array frame starts a
                // new row: rewind the array's key memo for replay.
                if matches!(self.stack.last(), Some(Frame::List { .. }))
                    && let Some(memo) = self.row_memos.last_mut()
                {
                    memo.cursor = 0;
                }
                let field_count = plan.fields.len();
                let mut values = self.values_pool.pop().unwrap_or_default();
                values.clear();
                values.resize(field_count, None);
                self.stack.push(Frame::Struct {
                    plan,
                    values,
                    awaiting: None,
                    skip_value: false,
                });
                Ok(())
            }
            PlanKind::Dict(_, value) => {
                self.stack.push(Frame::Dict {
                    map: PyDict::new(self.py),
                    pending: None,
                    value,
                });
                Ok(())
            }
            PlanKind::Any => self.begin_any(AnyEvent::StartObject, at, None),
            PlanKind::Custom(class) if self.dec_hook.is_some() => {
                let class = class.clone_ref(self.py);
                self.begin_any(AnyEvent::StartObject, at, Some(class))
            }
            _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
        }
    }

    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::Key(key), at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            return Ok(());
        }
        match self.stack.last_mut() {
            Some(Frame::Struct {
                plan,
                values,
                awaiting,
                skip_value,
            }) => {
                let raw = match key {
                    StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
                    StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
                };
                // D1 memo: replay the first row's resolution positionally.
                let mut resolved: Option<Option<usize>> = None;
                if let Some(memo) = self.row_memos.last_mut()
                    && !memo.disabled
                    && memo.complete
                {
                    match memo.entries.get(memo.cursor) {
                        Some((bytes, index)) if bytes.as_slice() == raw.as_ref() => {
                            memo.cursor += 1;
                            resolved = Some(*index);
                        }
                        _ => memo.disabled = true,
                    }
                }
                let looked_up = match resolved {
                    Some(index) => index,
                    None => {
                        let index = plan.by_wire.get(raw.as_ref()).copied();
                        if let Some(memo) = self.row_memos.last_mut()
                            && !memo.disabled
                            && !memo.complete
                        {
                            memo.entries.push((raw.clone().into_owned(), index));
                            memo.cursor += 1;
                        }
                        index
                    }
                };
                match looked_up {
                    Some(index) => {
                        if values[index].is_some() && self.strict {
                            return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
                        }
                        *awaiting = Some(index);
                        Ok(())
                    }
                    None if plan.forbid_unknown => {
                        Err(Fault::validation_at(FaultCode::UnknownField, at))
                    }
                    None => {
                        *skip_value = true;
                        Ok(())
                    }
                }
            }
            Some(Frame::Dict { pending, .. }) => {
                let converted = match key {
                    StringToken::Bare(bytes) => string_token_to_py(self.py, bytes, false),
                    StringToken::Quoted { inner, escaped } => {
                        string_token_to_py(self.py, inner, escaped)
                    }
                };
                *pending = Some(converted);
                Ok(())
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn end_object(&mut self, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::EndObject, at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            self.skip_depth -= 1;
            if self.skip_depth == 0 {
                self.clear_top_skip();
            }
            return Ok(());
        }
        match self.stack.pop() {
            Some(Frame::Struct { plan, values, .. }) => {
                let value = self.finish_struct(plan, values, at)?;
                // Closing a row (a struct directly under an array frame)
                // seals the memo: later rows replay it positionally.
                if matches!(self.stack.last(), Some(Frame::List { .. }))
                    && let Some(memo) = self.row_memos.last_mut()
                    && !memo.disabled
                {
                    memo.complete = true;
                }
                self.place(value, at)
            }
            Some(Frame::Dict { map, .. }) => self.place(map.into_any(), at),
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn start_array(&mut self, declared_len: usize, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::StartArray(declared_len), at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            self.skip_depth += 1;
            return Ok(());
        }
        if self.top_struct_skips() {
            self.skip_depth = 1;
            return Ok(());
        }
        let expected = self
            .expected_plan()
            .ok_or(Fault::syntax_at(FaultCode::Internal, at))?
            .resolve_container();
        match &expected.kind {
            PlanKind::List(item) => {
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(declared_len),
                    item,
                    as_tuple: false,
                });
                self.row_memos.push(RowMemo::default());
                Ok(())
            }
            PlanKind::TupleVar(item) => {
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(declared_len),
                    item,
                    as_tuple: true,
                });
                self.row_memos.push(RowMemo::default());
                Ok(())
            }
            PlanKind::Any => self.begin_any(AnyEvent::StartArray(declared_len), at, None),
            PlanKind::Custom(class) if self.dec_hook.is_some() => {
                let class = class.clone_ref(self.py);
                self.begin_any(AnyEvent::StartArray(declared_len), at, Some(class))
            }
            _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
        }
    }

    fn end_array(&mut self, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::EndArray, at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            self.skip_depth -= 1;
            if self.skip_depth == 0 {
                self.clear_top_skip();
            }
            return Ok(());
        }
        match self.stack.pop() {
            Some(Frame::List {
                items, as_tuple, ..
            }) => {
                self.row_memos.pop();
                let value = if as_tuple {
                    match PyTuple::new(self.py, items) {
                        Ok(tuple) => tuple.into_any(),
                        Err(err) => return Err(self.internal(err, at)),
                    }
                } else {
                    // The final list requested by the target type — not an
                    // intermediate container, deliberately not counted.
                    match PyList::new(self.py, items) {
                        Ok(list) => list.into_any(),
                        Err(err) => return Err(self.internal(err, at)),
                    }
                };
                self.place(value, at)
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault> {
        if self.any_forward(AnyEvent::Scalar(token), at)? {
            return Ok(());
        }
        if self.skip_depth > 0 {
            return Ok(());
        }
        if self.top_struct_skips() {
            self.clear_top_skip();
            return Ok(());
        }
        let expected = self
            .expected_plan()
            .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
        let value = self.convert_scalar(expected, token, at)?;
        self.place(value, at)
    }
}
