//! The typed consumer: constructs the requested target directly from parser
//! events (canvas AD-001, §9).
//!
//! Invariant: for a Struct target the frame stores one optional final value
//! per declared field — a constructor argument frame — never a mapping from
//! wire keys to values. No discardable dict/list tree exists at any point.

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict};

use crate::containers::{count_struct_instance, new_final_dict, new_final_list, new_final_tuple};
use crate::error::{Fault, FaultCode, Position};
use crate::event::{Consumer, ScalarToken, StringToken};
use crate::limits::reserve_elements;
use crate::plan::{CompiledPlan, DefaultPlan, PlanKind, StructPlan};
use crate::pyval::{float_from_digits, int_from_digits, scalar_to_py, string_token_to_py};
use crate::scalar::unescape;
use crate::untyped::UntypedConsumer;

/// Where a sequence frame finds the plan for its next element. `list[T]` and
/// `tuple[T, ...]` answer the same plan every time; `tuple[A, B, C]` answers by
/// position and runs out, which is what makes its length a type error rather
/// than a document property.
enum SequencePlan<'plan> {
    Uniform(&'plan CompiledPlan),
    ByPosition(&'plan [CompiledPlan]),
}

impl<'plan> SequencePlan<'plan> {
    fn at(&self, index: usize) -> Option<&'plan CompiledPlan> {
        match self {
            Self::Uniform(plan) => Some(plan),
            Self::ByPosition(plans) => plans.get(index),
        }
    }

    fn expected_length(&self) -> Option<usize> {
        match self {
            Self::Uniform(_) => None,
            Self::ByPosition(plans) => Some(plans.len()),
        }
    }
}

enum Frame<'py, 'plan> {
    Struct {
        plan: &'plan StructPlan,
        values: Vec<Option<Bound<'py, PyAny>>>,
        awaiting: Option<usize>,
        skip_value: bool,
    },
    List {
        items: Vec<Bound<'py, PyAny>>,
        item: SequencePlan<'plan>,
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
    /// Set by `begin_tabular` (optimization D5): every row of this array is
    /// emitted from one header, so a sealed memo replays positionally without
    /// re-reading key bytes. An untrusted sealed memo still verifies each key
    /// by byte comparison before replaying.
    trusted: bool,
}

impl RowMemo {
    /// A memo caches wire-name→field-index resolutions, which stay valid only
    /// while every row resolves against one plan. A fixed tuple gives each
    /// position its own plan, so an index recorded from one row can name a
    /// different field in the next — two Structs sharing field names in
    /// opposite declaration order silently swap values. Such a frame never
    /// memoizes; the rule lives here so no call site can forget it.
    fn for_sequence(item: &SequencePlan<'_>) -> Self {
        Self {
            disabled: matches!(item, SequencePlan::ByPosition(_)),
            ..Self::default()
        }
    }
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
            Some(Frame::List { items, item, .. }) => item.at(items.len()),
            Some(Frame::Dict { value, .. }) => Some(value),
            None => Some(self.root),
        }
    }

    /// The plan for the next value, or the fault that explains its absence.
    /// A saturated fixed tuple has no plan for another element — that is a
    /// length violation the caller should see, not an internal inconsistency.
    fn expected_plan_or_fault(&self, at: Position) -> Result<&'plan CompiledPlan, Fault> {
        if let Some(plan) = self.expected_plan() {
            return Ok(plan);
        }
        match self.stack.last() {
            Some(Frame::List { items, item, .. })
                if item.expected_length().is_some_and(|len| items.len() >= len) =>
            {
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
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
                    let candidate = candidate.bind(py);
                    // Category before equality. Python's `True == 1` is true and
                    // `bool` subclasses `int`, so equality alone lets a boolean
                    // satisfy `Literal[1]` — which msgspec rejects with
                    // "Expected `int`, got `bool`" (review F-07). Comparing the
                    // exact types first restores that boundary; msgspec permits
                    // only None, int, and str in a Literal, so there is no
                    // widening case this rejects wrongly.
                    if !value.get_type().is(candidate.get_type()) {
                        continue;
                    }
                    match value.eq(candidate) {
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
            | PlanKind::TupleFixed(_)
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
        // A kw_only class rejects positional arguments, so its plan carries the
        // field names and every value goes in the keyword half of the call: zero
        // positional, one names tuple built once at plan-compile time. Ordinary
        // classes keep the positional path with a null kwnames (review F-09).
        let (positional_count, keyword_names) = match &plan.keyword_names {
            Some(names) => (0, names.as_ptr()),
            None => (pointers.len(), std::ptr::null_mut()),
        };
        let raw = unsafe {
            pyo3::ffi::PyObject_Vectorcall(
                plan.class.as_ptr(),
                pointers.as_ptr(),
                positional_count,
                keyword_names,
            )
        };
        arguments.clear();
        self.arguments_scratch = arguments;
        count_struct_instance();
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
    fn begin_tabular(&mut self, _leaf_count: usize, _at: Position) -> Result<(), Fault> {
        // Inside an `Any` subtree or a skipped value the announcement is not
        // about a frame this consumer owns; the sub-consumer resolves keys by
        // hash and needs nothing from it.
        if self.any_sub.is_some() || self.skip_depth > 0 {
            return Ok(());
        }
        // A memo that declined to memoize stays declined: trusting it would
        // be a contradictory state even though the replay path checks
        // `disabled` first.
        if matches!(self.stack.last(), Some(Frame::List { .. }))
            && let Some(memo) = self.row_memos.last_mut()
            && !memo.disabled
        {
            memo.trusted = true;
        }
        Ok(())
    }

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
        let expected = self.expected_plan_or_fault(at)?.resolve_container();
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
                    map: new_final_dict(self.py),
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
                // D1 memo: replay the first row's resolution positionally.
                // A trusted memo (D5: the parser announced a tabular body,
                // whose rows are all emitted from one header) resolves
                // without reading the key bytes at all.
                let mut replayed: Option<Option<usize>> = None;
                if let Some(memo) = self.row_memos.last_mut()
                    && !memo.disabled
                    && memo.complete
                    && memo.trusted
                {
                    match memo.entries.get(memo.cursor) {
                        Some((_, index)) => {
                            memo.cursor += 1;
                            replayed = Some(*index);
                        }
                        None => memo.disabled = true,
                    }
                }
                let looked_up = match replayed {
                    Some(index) => index,
                    None => {
                        let raw = match key {
                            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
                            StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
                        };
                        let mut verified: Option<Option<usize>> = None;
                        if let Some(memo) = self.row_memos.last_mut()
                            && !memo.disabled
                            && memo.complete
                        {
                            match memo.entries.get(memo.cursor) {
                                Some((bytes, index)) if bytes.as_slice() == raw.as_ref() => {
                                    memo.cursor += 1;
                                    verified = Some(*index);
                                }
                                _ => memo.disabled = true,
                            }
                        }
                        match verified {
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
                        }
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
        let expected = self.expected_plan_or_fault(at)?.resolve_container();
        match &expected.kind {
            PlanKind::List(item) => {
                let item = SequencePlan::Uniform(item);
                self.row_memos.push(RowMemo::for_sequence(&item));
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(reserve_elements(declared_len)),
                    item,
                    as_tuple: false,
                });
                Ok(())
            }
            PlanKind::TupleVar(item) => {
                let item = SequencePlan::Uniform(item);
                self.row_memos.push(RowMemo::for_sequence(&item));
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(reserve_elements(declared_len)),
                    item,
                    as_tuple: true,
                });
                Ok(())
            }
            PlanKind::TupleFixed(plans) => {
                // The length is known from the type, so the reservation comes
                // from the plan and never from the document's declared count.
                let item = SequencePlan::ByPosition(plans);
                self.row_memos.push(RowMemo::for_sequence(&item));
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(plans.len()),
                    item,
                    as_tuple: true,
                });
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
                items,
                item,
                as_tuple,
            }) => {
                self.row_memos.pop();
                if item.expected_length().is_some_and(|len| items.len() != len) {
                    return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                }
                let value = if as_tuple {
                    match new_final_tuple(self.py, items) {
                        Ok(tuple) => tuple.into_any(),
                        Err(err) => return Err(self.internal(err, at)),
                    }
                } else {
                    // The sequence the target type asked for, counted as final
                    // output rather than an intermediate container.
                    match new_final_list(self.py, items) {
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
        let expected = self.expected_plan_or_fault(at)?;
        let value = self.convert_scalar(expected, token, at)?;
        self.place(value, at)
    }
}
