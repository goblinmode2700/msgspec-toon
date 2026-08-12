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
use crate::event::{Consumer, ObjectProbe, ObjectSelectionResult, ScalarToken, StringToken};
use crate::limits::reserve_elements;
use crate::parser::classify_value;
use crate::plan::{
    CompiledPlan, Constraints, DefaultPlan, FieldAction, FieldActionKind, PlanId, PlanKind,
    StructPlan, TagValue,
};
use crate::pyval::{float_from_digits, int_from_digits, scalar_to_py, string_token_to_py};
use crate::scalar::unescape;
use crate::untyped::UntypedConsumer;

/// Where a sequence frame finds the plan for its next element. `list[T]` and
/// `tuple[T, ...]` answer the same plan every time; `tuple[A, B, C]` answers by
/// position and runs out, which is what makes its length a type error rather
/// than a document property.
enum SequencePlan<'plan> {
    Uniform(PlanId),
    ByPosition(&'plan [PlanId]),
}

impl<'plan> SequencePlan<'plan> {
    fn at(&self, index: usize) -> Option<PlanId> {
        match self {
            Self::Uniform(plan) => Some(*plan),
            Self::ByPosition(plans) => plans.get(index).copied(),
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
    ArrayStruct {
        plan: &'plan StructPlan,
        values: Vec<Option<Bound<'py, PyAny>>>,
        next: usize,
        tag_pending: bool,
    },
    ArrayStructUnion {
        members: &'plan [PlanId],
    },
    List {
        items: Vec<Bound<'py, PyAny>>,
        item: SequencePlan<'plan>,
        as_tuple: bool,
        constraints: Option<&'plan Constraints>,
    },
    Dict {
        map: Bound<'py, PyDict>,
        pending: Option<Bound<'py, PyAny>>,
        value: PlanId,
        constraints: Option<&'plan Constraints>,
    },
}

#[derive(Default)]
pub enum TypedObjectSelection {
    #[default]
    Passthrough,
    SelectedPlan(PlanId),
    InvalidTag,
    Skip,
    StructField {
        index: usize,
        selected_plan: PlanId,
    },
}

fn scalar_text(token: ScalarToken<'_>) -> Option<std::borrow::Cow<'_, [u8]>> {
    match token {
        ScalarToken::BareString(bytes) => Some(std::borrow::Cow::Borrowed(bytes)),
        ScalarToken::Quoted { inner, escaped } => Some(unescape(inner, escaped)),
        _ => None,
    }
}

/// Compare a discriminator with the compiled native tag. Category is part of
/// the match, so Python's cross-type equality (`True == 1`, `1.0 == 1`) never
/// selects an integer-tagged variant.
fn tag_matches(tag: &TagValue, token: ScalarToken<'_>) -> bool {
    match (tag, token) {
        (TagValue::String(expected), ScalarToken::BareString(actual)) => expected == actual,
        (TagValue::String(expected), ScalarToken::Quoted { inner, escaped }) => {
            expected.as_slice() == unescape(inner, escaped).as_ref()
        }
        (TagValue::Integer(expected), ScalarToken::Integer(digits)) => {
            // SAFETY: the document has passed UTF-8 validation, and the
            // integer classifier admits only the ASCII JSON integer grammar.
            let text = unsafe { std::str::from_utf8_unchecked(digits) };
            text.parse::<i64>().ok().as_ref() == Some(expected)
        }
        _ => false,
    }
}

fn scalar_plan_exactly_matches(kind: &PlanKind, token: ScalarToken<'_>) -> bool {
    matches!(
        (kind, token),
        (PlanKind::NoneT, ScalarToken::Null)
            | (PlanKind::Bool, ScalarToken::Bool(_))
            | (PlanKind::Int, ScalarToken::Integer(_))
            | (PlanKind::Float, ScalarToken::Float(_))
            | (
                PlanKind::Str,
                ScalarToken::BareString(_) | ScalarToken::Quoted { .. }
            )
    )
}

fn scalar_plan_fallback_rank(kind: &PlanKind) -> u8 {
    match kind {
        PlanKind::Int => 0,
        PlanKind::Float => 1,
        PlanKind::Bool => 2,
        PlanKind::Str => 3,
        _ => 4,
    }
}

/// Normalize a JSON-number string to exact integer digits when its value is
/// integral. This never routes a large integer or exponent through `f64`.
fn exact_integer_text(text: &[u8]) -> Option<Vec<u8>> {
    let mut cursor = usize::from(text.first() == Some(&b'-'));
    let negative = cursor == 1;
    let integer_start = cursor;
    if cursor >= text.len() || !text[cursor].is_ascii_digit() {
        return None;
    }
    if text[cursor] == b'0' && text.get(cursor + 1).is_some_and(u8::is_ascii_digit) {
        return None;
    }
    while text.get(cursor).is_some_and(u8::is_ascii_digit) {
        cursor += 1;
    }
    let integer_digits = cursor - integer_start;
    let mut digits = text[integer_start..cursor].to_vec();
    if text.get(cursor) == Some(&b'.') {
        cursor += 1;
        let fraction_start = cursor;
        while text.get(cursor).is_some_and(u8::is_ascii_digit) {
            digits.push(text[cursor]);
            cursor += 1;
        }
        if cursor == fraction_start {
            return None;
        }
    }
    let mut exponent = 0i32;
    if matches!(text.get(cursor), Some(b'e' | b'E')) {
        cursor += 1;
        let exponent_negative = if text.get(cursor) == Some(&b'-') {
            cursor += 1;
            true
        } else if text.get(cursor) == Some(&b'+') {
            cursor += 1;
            false
        } else {
            false
        };
        let start = cursor;
        while let Some(byte) = text.get(cursor).filter(|byte| byte.is_ascii_digit()) {
            exponent = exponent
                .checked_mul(10)?
                .checked_add(i32::from(*byte - b'0'))?;
            cursor += 1;
        }
        if cursor == start {
            return None;
        }
        if exponent_negative {
            exponent = -exponent;
        }
    }
    if cursor != text.len() {
        return None;
    }
    let decimal = i64::try_from(integer_digits).ok()? + i64::from(exponent);
    if decimal <= 0 {
        if digits.iter().all(|digit| *digit == b'0') {
            return Some(b"0".to_vec());
        }
        return None;
    }
    let decimal = usize::try_from(decimal).ok()?;
    if decimal < digits.len() {
        if digits[decimal..].iter().any(|digit| *digit != b'0') {
            return None;
        }
        digits.truncate(decimal);
    } else if decimal > digits.len() {
        digits.resize(decimal.min(1_000_000), b'0');
        if decimal > 1_000_000 {
            return None;
        }
    }
    while digits.len() > 1 && digits[0] == b'0' {
        digits.remove(0);
    }
    if negative && digits.iter().any(|digit| *digit != b'0') {
        digits.insert(0, b'-');
    }
    Some(digits)
}

/// Optimization D1: rows of one array repeat an identical key-event
/// sequence, so the first row's wire-name→field-index resolutions are
/// recorded and replayed positionally for every later row — a byte
/// comparison instead of a hash lookup per cell. Any sequence deviation
/// disables the memo for that array and falls back to hashing.
#[derive(Default)]
struct RowMemo {
    entries: Vec<(Vec<u8>, FieldAction)>,
    cursor: usize,
    complete: bool,
    disabled: bool,
    /// Set by `begin_tabular` (optimization D5): every row of this array is
    /// emitted from one header, so a sealed memo replays positionally without
    /// re-reading key bytes. An untrusted sealed memo still verifies each key
    /// by byte comparison before replaying.
    trusted: bool,
    /// Tagged nested-field selection learned from the first row. The header
    /// fixes both the parent field and discriminator cell for the body; only
    /// the discriminator value and union member remain row-dependent.
    tagged_selections: Vec<Option<TaggedSelectionMemo>>,
}

#[derive(Clone, Copy)]
struct TaggedSelectionMemo {
    index: usize,
    declared: PlanId,
    tag_cell: Option<usize>,
    skip_field: Option<usize>,
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

pub struct TypedConsumer<'py, 'plan, const EXTENDED: bool = false> {
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
    has_tagged_plans: bool,
    has_array_tags: bool,
}

impl<'py, 'plan, const EXTENDED: bool> TypedConsumer<'py, 'plan, EXTENDED> {
    pub fn new(
        py: Python<'py>,
        root: &'plan CompiledPlan,
        strict: bool,
        dec_hook: Option<Py<PyAny>>,
        float_hook: Option<Py<PyAny>>,
    ) -> Self {
        let has_tagged_plans = EXTENDED
            && root.nodes.iter().any(|node| match &node.kind {
                PlanKind::Struct(plan) => plan.tag_field.is_some(),
                PlanKind::Union(union) => union.members.len() > 1,
                _ => false,
            });
        let has_array_tags = EXTENDED
            && root.nodes.iter().any(|node| {
                matches!(
                    &node.kind,
                    PlanKind::Struct(plan) if plan.array_like && plan.tag_value.is_some()
                )
            });
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
            has_tagged_plans,
            has_array_tags,
        }
    }

    pub fn take_result(&mut self) -> Option<Bound<'py, PyAny>> {
        self.result.take()
    }

    fn internal(&mut self, err: PyErr, at: Position) -> Fault {
        self.pending_err = Some(err);
        Fault::syntax_at(FaultCode::Internal, at)
    }

    fn expected_plan(&self) -> Option<PlanId> {
        match self.stack.last() {
            Some(Frame::Struct {
                plan,
                awaiting: Some(index),
                ..
            }) => Some(plan.fields[*index].value),
            Some(Frame::Struct { .. }) => None,
            Some(Frame::ArrayStruct {
                plan,
                next,
                tag_pending,
                ..
            }) => {
                if *tag_pending {
                    None
                } else {
                    plan.fields.get(*next).map(|field| field.value)
                }
            }
            Some(Frame::ArrayStructUnion { .. }) => None,
            Some(Frame::List { items, item, .. }) => item.at(items.len()),
            Some(Frame::Dict { value, .. }) => Some(*value),
            None => Some(self.root.root),
        }
    }

    /// The plan for the next value, or the fault that explains its absence.
    /// A saturated fixed tuple has no plan for another element — that is a
    /// length violation the caller should see, not an internal inconsistency.
    fn expected_plan_or_fault(&self, at: Position) -> Result<PlanId, Fault> {
        if let Some(plan) = self.expected_plan() {
            return Ok(plan);
        }
        match self.stack.last() {
            Some(Frame::List { items, item, .. })
                if item.expected_length().is_some_and(|len| items.len() >= len) =>
            {
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            Some(Frame::ArrayStruct { .. } | Frame::ArrayStructUnion { .. }) => {
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
            Some(Frame::ArrayStruct { values, next, .. }) => {
                values[*next] = Some(value);
                *next += 1;
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
            Some(Frame::ArrayStructUnion { .. }) => {
                return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
            }
            None => self.result = Some(value),
        }
        Ok(())
    }

    fn convert_scalar(
        &mut self,
        plan: PlanId,
        token: ScalarToken<'_>,
        at: Position,
    ) -> Result<Bound<'py, PyAny>, Fault> {
        let py = self.py;
        match &self.root.node(plan).kind {
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
                ScalarToken::Integer(b"0") if !self.strict => {
                    Ok(PyBool::new(py, false).to_owned().into_any())
                }
                ScalarToken::Integer(b"1") if !self.strict => {
                    Ok(PyBool::new(py, true).to_owned().into_any())
                }
                _ if !self.strict => match scalar_text(token).as_deref() {
                    Some(b"true" | b"True" | b"TRUE" | b"1") => {
                        Ok(PyBool::new(py, true).to_owned().into_any())
                    }
                    Some(b"false" | b"False" | b"FALSE" | b"0" | b"-0") => {
                        Ok(PyBool::new(py, false).to_owned().into_any())
                    }
                    _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
                },
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Int => match token {
                ScalarToken::Integer(digits) => {
                    let value =
                        int_from_digits(py, digits).map_err(|err| self.internal(err, at))?;
                    self.validate_scalar(plan, value, at)
                }
                _ if !self.strict => {
                    let Some(text) = scalar_text(token) else {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    };
                    if text.iter().any(|byte| matches!(byte, b'.' | b'e' | b'E')) {
                        let value = float_from_digits(py, &text, None)
                            .map_err(|_| Fault::validation_at(FaultCode::TypeMismatch, at))?;
                        let number = value
                            .extract::<f64>()
                            .map_err(|err| self.internal(err, at))?;
                        if !number.is_finite()
                            || number.fract() != 0.0
                            || number.abs() > 9_007_199_254_740_992.0
                        {
                            return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                        }
                        let integer = value
                            .call_method0("__int__")
                            .map_err(|err| self.internal(err, at))?;
                        return self.validate_scalar(plan, integer, at);
                    }
                    let Some(digits) = exact_integer_text(&text) else {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    };
                    let value =
                        int_from_digits(py, &digits).map_err(|err| self.internal(err, at))?;
                    self.validate_scalar(plan, value, at)
                }
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Float => match token {
                ScalarToken::Integer(digits) | ScalarToken::Float(digits) => {
                    let value = float_from_digits(py, digits, self.float_hook.as_ref())
                        .map_err(|err| self.internal(err, at))?;
                    self.validate_scalar(plan, value, at)
                }
                _ if !self.strict => {
                    let Some(text) = scalar_text(token) else {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    };
                    let value = float_from_digits(py, &text, self.float_hook.as_ref())
                        .map_err(|_| Fault::validation_at(FaultCode::TypeMismatch, at))?;
                    self.validate_scalar(plan, value, at)
                }
                _ => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
            },
            PlanKind::Str => match token {
                ScalarToken::BareString(bytes) => {
                    let value = string_token_to_py(py, bytes, false);
                    self.validate_scalar(plan, value, at)
                }
                ScalarToken::Quoted { inner, escaped } => {
                    let value = string_token_to_py(py, inner, escaped);
                    self.validate_scalar(plan, value, at)
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
                // msgspec chooses an exact scalar category before a widening
                // conversion. In particular, `float | int` decodes `1` as an
                // int even though the float plan can also accept integer
                // tokens. The second pass preserves that widening only when
                // no exact member exists, as in `float | str`.
                for &member in &union.members {
                    if !scalar_plan_exactly_matches(&self.root.node(member).kind, token) {
                        continue;
                    }
                    match self.convert_scalar(member, token, at) {
                        Ok(value) => return Ok(value),
                        Err(fault) if fault.code == FaultCode::TypeMismatch => continue,
                        Err(fault) => return Err(fault),
                    }
                }
                // In permissive mode msgspec's scalar conversion priority is
                // int, float, then bool, independent of union declaration
                // order. This makes `float | int` decode the string "1" as
                // int, while `bool | float` decodes it as float.
                for rank in 0..=4 {
                    for &member in &union.members {
                        let kind = &self.root.node(member).kind;
                        if scalar_plan_exactly_matches(kind, token)
                            || scalar_plan_fallback_rank(kind) != rank
                        {
                            continue;
                        }
                        match self.convert_scalar(member, token, at) {
                            Ok(value) => return Ok(value),
                            Err(fault) if fault.code == FaultCode::TypeMismatch => continue,
                            Err(fault) => return Err(fault),
                        }
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
                    // "Expected `int`, got `bool`". Comparing the
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
            PlanKind::NativeScalar(class) => {
                let Some(hook) = self.dec_hook.as_ref() else {
                    return Err(Fault::validation_at(FaultCode::UnsupportedType, at));
                };
                let raw = match scalar_to_py(py, token, self.float_hook.as_ref()) {
                    Ok(value) => value,
                    Err(err) => return Err(self.internal(err, at)),
                };
                let hook = hook.clone_ref(py);
                let class = class.clone_ref(py);
                match hook.bind(py).call1((class, raw)) {
                    Ok(value) => self.validate_scalar(plan, value, at),
                    // msgspec conversion errors may include the rejected
                    // scalar. Discard them at this boundary and return the
                    // codec's coordinate-only validation fault.
                    Err(_) => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
                }
            }
            PlanKind::List(_)
            | PlanKind::TupleVar(_)
            | PlanKind::TupleFixed(_)
            | PlanKind::Dict(_, _)
            | PlanKind::Struct(_) => Err(Fault::validation_at(FaultCode::TypeMismatch, at)),
        }
    }

    fn validate_scalar(
        &mut self,
        plan: PlanId,
        value: Bound<'py, PyAny>,
        at: Position,
    ) -> Result<Bound<'py, PyAny>, Fault> {
        let Some(constraints) = &self.root.node(plan).constraints else {
            return Ok(value);
        };
        match constraints.scalar_valid(&value) {
            Ok(true) => Ok(value),
            Ok(false) => Err(Fault::validation_at(FaultCode::Constraint, at)),
            Err(err) => Err(self.internal(err, at)),
        }
    }

    fn validate_length(
        constraints: Option<&Constraints>,
        length: usize,
        at: Position,
    ) -> Result<(), Fault> {
        if constraints.is_some_and(|constraints| !constraints.length_valid(length)) {
            Err(Fault::validation_at(FaultCode::Constraint, at))
        } else {
            Ok(())
        }
    }

    /// Consume the discriminator before ordinary positional field placement.
    /// This ports msgspec's `tag_already_read` boundary without adopting its
    /// private Struct allocation: concrete plans validate the tag, while a
    /// union selects its compiled Struct plan, then both continue through the
    /// same public-constructor ArrayStruct frame.
    fn consume_array_tag(&mut self, token: ScalarToken<'_>, at: Position) -> Result<bool, Fault> {
        let mut candidates: smallvec::SmallVec<[&'plan StructPlan; 4]> = smallvec::SmallVec::new();
        let selects_union = match self.stack.last() {
            Some(Frame::ArrayStruct {
                plan,
                tag_pending: true,
                ..
            }) => {
                candidates.push(plan);
                false
            }
            Some(Frame::ArrayStructUnion { members }) => {
                for &member in *members {
                    let PlanKind::Struct(plan) = &self.root.node(member).kind else {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    };
                    if !plan.array_like || plan.tag_value.is_none() {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    }
                    candidates.push(plan);
                }
                true
            }
            _ => return Ok(false),
        };

        let mut selected = None;
        for plan in candidates {
            let Some(tag) = &plan.tag_value else {
                continue;
            };
            if tag_matches(tag, token) {
                selected = Some(plan);
                break;
            }
        }
        let selected = selected.ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?;

        if selects_union {
            let mut values = self.values_pool.pop().unwrap_or_default();
            values.clear();
            values.resize(selected.fields.len(), None);
            let frame = self
                .stack
                .last_mut()
                .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
            *frame = Frame::ArrayStruct {
                plan: selected,
                values,
                next: 0,
                tag_pending: false,
            };
        } else if let Some(Frame::ArrayStruct { tag_pending, .. }) = self.stack.last_mut() {
            *tag_pending = false;
        } else {
            return Err(Fault::syntax_at(FaultCode::Internal, at));
        }
        Ok(true)
    }

    fn lookup_field_action(
        plan: &StructPlan,
        mut memo: Option<&mut RowMemo>,
        key: StringToken<'_>,
    ) -> FieldAction {
        // D1 memo: replay the first row's resolution positionally. A trusted
        // tabular memo resolves without reading the repeated key bytes.
        if let Some(memo) = memo.as_deref_mut()
            && !memo.disabled
            && memo.complete
            && memo.trusted
        {
            match memo.entries.get(memo.cursor) {
                Some((_, index)) => {
                    memo.cursor += 1;
                    return *index;
                }
                None => memo.disabled = true,
            }
        }

        let raw = match key {
            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
            StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
        };
        if let Some(memo) = memo.as_deref_mut()
            && !memo.disabled
            && memo.complete
        {
            match memo.entries.get(memo.cursor) {
                Some((bytes, index)) if bytes.as_slice() == raw.as_ref() => {
                    memo.cursor += 1;
                    return *index;
                }
                _ => memo.disabled = true,
            }
        }

        let action = plan.field_action(raw.as_ref());
        if let Some(memo) = memo
            && !memo.disabled
            && !memo.complete
        {
            memo.entries.push((raw.into_owned(), action));
            memo.cursor += 1;
        }
        action
    }

    fn start_object_for_plan(&mut self, declared: PlanId, at: Position) -> Result<(), Fault> {
        let expected = self.root.resolve_container(declared);
        self.start_selected_object_plan(expected, at)
    }

    fn select_nested_tagged_plan(
        &self,
        declared: PlanId,
        raw_tag: Option<&[u8]>,
        at: Position,
    ) -> Result<PlanId, Fault> {
        match &self.root.node(declared).kind {
            PlanKind::Struct(plan) if EXTENDED && plan.tag_field.is_some() => {
                if let Some(raw) = raw_tag {
                    let token = classify_value(raw, at)?;
                    let tag = plan
                        .tag_value
                        .as_ref()
                        .ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?;
                    if !tag_matches(tag, token) {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    }
                }
                Ok(declared)
            }
            PlanKind::Union(union) if EXTENDED && union.members.len() > 1 => {
                let token = classify_value(
                    raw_tag.ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?,
                    at,
                )?;
                union
                    .members
                    .iter()
                    .copied()
                    .find(|&member| {
                        let PlanKind::Struct(plan) = &self.root.node(member).kind else {
                            return false;
                        };
                        plan.tag_value
                            .as_ref()
                            .is_some_and(|tag| tag_matches(tag, token))
                    })
                    .ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            _ => Ok(self.root.resolve_container(declared)),
        }
    }

    fn start_selected_object_plan(&mut self, expected: PlanId, at: Position) -> Result<(), Fault> {
        let expected_node = self.root.node(expected);
        match &expected_node.kind {
            PlanKind::Struct(plan) if !plan.array_like => {
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
                    value: *value,
                    constraints: expected_node.constraints.as_deref(),
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

    #[inline(always)]
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
        // classes keep the positional path with a null kwnames.
        let (positional_count, keyword_names) = match &plan.keyword_names {
            Some(names) => (0, names.as_ptr()),
            None => (pointers.len(), std::ptr::null_mut()),
        };
        // SAFETY: every pointer is borrowed from `arguments`, which remains
        // live until the call returns. `keyword_names` is a plan-owned tuple
        // pinned by the compiled plan. Vectorcall borrows argument pointers
        // and returns one new reference or null with a Python exception.
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
        // SAFETY: `PyObject_Vectorcall` returns a new reference on success;
        // this is the single owner transfer into PyO3. Null is converted to
        // the active Python exception without stealing any argument.
        unsafe { Bound::from_owned_ptr_or_err(py, raw) }.map_err(|err| self.internal(err, at))
    }

    /// Route an event into the untyped sub-consumer while inside an `Any`
    /// subtree; returns true when the event was consumed.
    #[cold]
    #[inline(never)]
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

impl<const EXTENDED: bool> Consumer for TypedConsumer<'_, '_, EXTENDED> {
    type ObjectSelection = TypedObjectSelection;

    fn needs_object_preflight(&self) -> bool {
        if !EXTENDED || !self.has_tagged_plans {
            return false;
        }
        let Some(index) = self.expected_plan() else {
            return false;
        };
        match &self.root.node(index).kind {
            PlanKind::Struct(plan) => plan.tag_field.is_some(),
            PlanKind::Union(union) => union.members.len() > 1,
            _ => false,
        }
    }

    fn object_scalar_hint(
        &mut self,
        selection: &mut Self::ObjectSelection,
        key: StringToken<'_>,
        value: ScalarToken<'_>,
        _at: Position,
    ) -> Result<(), Fault> {
        let Some(declared) = self.expected_plan() else {
            return Ok(());
        };
        let key = match key {
            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
            StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
        };
        let members: smallvec::SmallVec<[PlanId; 4]> = match &self.root.node(declared).kind {
            PlanKind::Struct(plan) if plan.tag_field.as_deref() == Some(key.as_ref()) => {
                smallvec::smallvec![declared]
            }
            PlanKind::Union(union) if union.members.len() > 1 => union
                .members
                .iter()
                .copied()
                .filter(|&member| {
                    matches!(
                        &self.root.node(member).kind,
                        PlanKind::Struct(plan)
                            if plan.tag_field.as_deref() == Some(key.as_ref())
                    )
                })
                .collect(),
            _ => return Ok(()),
        };
        if members.is_empty() {
            return Ok(());
        }
        for member in members {
            let PlanKind::Struct(plan) = &self.root.node(member).kind else {
                continue;
            };
            if plan.tag_field.as_deref() != Some(key.as_ref()) {
                continue;
            }
            let Some(tag) = &plan.tag_value else {
                continue;
            };
            if tag_matches(tag, value) {
                *selection = TypedObjectSelection::SelectedPlan(member);
                return Ok(());
            }
        }
        *selection = TypedObjectSelection::InvalidTag;
        Ok(())
    }

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
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::StartObject, at)?;
            debug_assert!(consumed);
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
        let declared = self.expected_plan_or_fault(at)?;
        self.start_object_for_plan(declared, at)
    }

    fn start_selected_object(
        &mut self,
        selection: Self::ObjectSelection,
        at: Position,
    ) -> Result<(), Fault> {
        match selection {
            TypedObjectSelection::SelectedPlan(plan) => self.start_selected_object_plan(plan, at),
            TypedObjectSelection::InvalidTag => {
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            TypedObjectSelection::Passthrough => self.start_object(at),
            TypedObjectSelection::Skip | TypedObjectSelection::StructField { .. } => {
                Err(Fault::syntax_at(FaultCode::Internal, at))
            }
        }
    }

    fn start_object_field(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() || self.skip_depth > 0 {
            self.key(key, at)?;
            return self.start_object(at);
        }

        let strict = self.strict;
        let declared = match self.stack.last_mut() {
            Some(Frame::Struct {
                plan,
                values,
                awaiting,
                skip_value,
            }) => {
                let action = Self::lookup_field_action(plan, self.row_memos.last_mut(), key);
                match action.kind() {
                    FieldActionKind::Tag => {
                        *skip_value = true;
                        None
                    }
                    FieldActionKind::Field => {
                        let index = action.field_index();
                        if values[index].is_some() && strict {
                            return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
                        }
                        *awaiting = Some(index);
                        Some(plan.fields[index].value)
                    }
                    FieldActionKind::Reject => {
                        return Err(Fault::validation_at(FaultCode::UnknownField, at));
                    }
                    FieldActionKind::Skip => {
                        *skip_value = true;
                        None
                    }
                }
            }
            _ => {
                self.key(key, at)?;
                return self.start_object(at);
            }
        };

        let Some(declared) = declared else {
            return self.start_object(at);
        };
        self.start_object_for_plan(declared, at)
    }

    #[inline(never)]
    fn select_object_field(
        &mut self,
        key: StringToken<'_>,
        probe: ObjectProbe<'_, '_>,
        at: Position,
    ) -> Result<ObjectSelectionResult<Self::ObjectSelection>, Fault> {
        if self.any_sub.is_some() || self.skip_depth > 0 {
            return Ok(ObjectSelectionResult::new(
                TypedObjectSelection::Passthrough,
            ));
        }

        let memoized = self.row_memos.last_mut().and_then(|memo| {
            if memo.disabled || !memo.complete || !memo.trusted {
                return None;
            }
            let selection = memo.tagged_selections.get(memo.cursor).copied().flatten();
            if selection.is_some() {
                // This replaces the parent field lookup that normally moves
                // the positional row memo forward by one entry.
                memo.cursor += 1;
            }
            selection
        });
        if let Some(memoized) = memoized {
            let Some(Frame::Struct { values, .. }) = self.stack.last_mut() else {
                return Err(Fault::syntax_at(FaultCode::Internal, at));
            };
            if values[memoized.index].is_some() && self.strict {
                return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
            }
            let raw_tag = match memoized.tag_cell {
                Some(cell) => Some(
                    probe
                        .raw_cell(cell)
                        .ok_or(Fault::syntax_at(FaultCode::Internal, at))?,
                ),
                None => None,
            };
            let selected_plan = self.select_nested_tagged_plan(memoized.declared, raw_tag, at)?;
            return Ok(ObjectSelectionResult {
                selection: TypedObjectSelection::StructField {
                    index: memoized.index,
                    selected_plan,
                },
                skip_field: memoized.skip_field,
                disposition: crate::event::ObjectFieldDisposition::Emit,
            });
        }

        let strict = self.strict;
        let memo_slot = self.row_memos.last().map(|memo| memo.cursor);
        let (index, declared) = match self.stack.last_mut() {
            Some(Frame::Struct { plan, values, .. }) => {
                let action = Self::lookup_field_action(plan, self.row_memos.last_mut(), key);
                match action.kind() {
                    FieldActionKind::Tag => {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    }
                    FieldActionKind::Field => {
                        let index = action.field_index();
                        if values[index].is_some() && strict {
                            return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
                        }
                        (index, plan.fields[index].value)
                    }
                    FieldActionKind::Reject => {
                        return Err(Fault::validation_at(FaultCode::UnknownField, at));
                    }
                    FieldActionKind::Skip => {
                        return Ok(ObjectSelectionResult::validate_only(
                            TypedObjectSelection::Skip,
                        ));
                    }
                }
            }
            _ => {
                return Ok(ObjectSelectionResult::new(
                    TypedObjectSelection::Passthrough,
                ));
            }
        };

        let mut skip_field = None;
        let mut tag_cell = None;
        let mut tagged_selection = false;
        let selected_plan = match &self.root.node(declared).kind {
            PlanKind::Struct(plan) if EXTENDED && plan.tag_field.is_some() => {
                tagged_selection = true;
                let tag_field = plan.tag_field.as_deref().expect("checked above");
                let mut matching_tag = None;
                for (field_index, cell_index, probe_key, raw) in probe.scalar_cells() {
                    let probe_key = match probe_key {
                        StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
                        StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
                    };
                    if probe_key.as_ref() == tag_field {
                        matching_tag = Some(classify_value(raw, at)?);
                        skip_field = Some(field_index);
                        tag_cell = Some(cell_index);
                        break;
                    }
                }
                if let Some(token) = matching_tag {
                    let tag = plan
                        .tag_value
                        .as_ref()
                        .ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?;
                    if !tag_matches(tag, token) {
                        return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                    }
                }
                declared
            }
            PlanKind::Union(union) if EXTENDED && union.members.len() > 1 => {
                tagged_selection = true;
                let tag_field =
                    union
                        .members
                        .iter()
                        .find_map(|&member| match &self.root.node(member).kind {
                            PlanKind::Struct(plan) => plan.tag_field.as_deref(),
                            _ => None,
                        });
                let tag_field =
                    tag_field.ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?;
                let mut tag_token = None;
                for (field_index, cell_index, probe_key, raw) in probe.scalar_cells() {
                    let probe_key = match probe_key {
                        StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
                        StringToken::Quoted { inner, escaped } => unescape(inner, escaped),
                    };
                    if probe_key.as_ref() == tag_field {
                        tag_token = Some(classify_value(raw, at)?);
                        skip_field = Some(field_index);
                        tag_cell = Some(cell_index);
                        break;
                    }
                }
                let token = tag_token.ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?;
                let mut selected = None;
                for &member in &union.members {
                    let PlanKind::Struct(plan) = &self.root.node(member).kind else {
                        continue;
                    };
                    let Some(tag) = &plan.tag_value else {
                        continue;
                    };
                    if tag_matches(tag, token) {
                        selected = Some(member);
                        break;
                    }
                }
                selected.ok_or(Fault::validation_at(FaultCode::TypeMismatch, at))?
            }
            _ => self.root.resolve_container(declared),
        };

        if tagged_selection
            && let (Some(slot), Some(memo)) = (memo_slot, self.row_memos.last_mut())
            && !memo.disabled
            && !memo.complete
        {
            if memo.tagged_selections.len() <= slot {
                memo.tagged_selections.resize(slot + 1, None);
            }
            memo.tagged_selections[slot] = Some(TaggedSelectionMemo {
                index,
                declared,
                tag_cell,
                skip_field,
            });
        }

        Ok(ObjectSelectionResult {
            selection: TypedObjectSelection::StructField {
                index,
                selected_plan,
            },
            skip_field,
            disposition: crate::event::ObjectFieldDisposition::Emit,
        })
    }

    fn start_selected_object_field(
        &mut self,
        key: StringToken<'_>,
        selection: Self::ObjectSelection,
        at: Position,
    ) -> Result<(), Fault> {
        match selection {
            TypedObjectSelection::Passthrough => self.start_object_field(key, at),
            TypedObjectSelection::SelectedPlan(_) | TypedObjectSelection::InvalidTag => {
                Err(Fault::syntax_at(FaultCode::Internal, at))
            }
            TypedObjectSelection::Skip => {
                let Some(Frame::Struct { skip_value, .. }) = self.stack.last_mut() else {
                    return Err(Fault::syntax_at(FaultCode::Internal, at));
                };
                *skip_value = true;
                self.start_object(at)
            }
            TypedObjectSelection::StructField {
                index,
                selected_plan,
            } => {
                let Some(Frame::Struct { awaiting, .. }) = self.stack.last_mut() else {
                    return Err(Fault::syntax_at(FaultCode::Internal, at));
                };
                *awaiting = Some(index);
                self.start_selected_object_plan(selected_plan, at)
            }
        }
    }

    fn end_object_field(&mut self, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() || self.skip_depth > 0 {
            return self.end_object(at);
        }

        let struct_pair = matches!(
            self.stack.as_slice(),
            [.., Frame::Struct { .. }, Frame::Struct { .. }]
        );
        if !struct_pair {
            return self.end_object(at);
        }

        let Some(Frame::Struct { plan, values, .. }) = self.stack.pop() else {
            unreachable!("struct_pair checked above")
        };
        let value = self.finish_struct(plan, values, at)?;
        match self.stack.last_mut() {
            Some(Frame::Struct {
                values, awaiting, ..
            }) => {
                let index = awaiting
                    .take()
                    .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
                values[index] = Some(value);
                Ok(())
            }
            _ => unreachable!("struct_pair checked above"),
        }
    }

    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::Key(key), at)?;
            debug_assert!(consumed);
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
                let action = Self::lookup_field_action(plan, self.row_memos.last_mut(), key);
                match action.kind() {
                    FieldActionKind::Tag | FieldActionKind::Skip => {
                        *skip_value = true;
                        Ok(())
                    }
                    FieldActionKind::Field => {
                        let index = action.field_index();
                        if values[index].is_some() && self.strict {
                            return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
                        }
                        *awaiting = Some(index);
                        Ok(())
                    }
                    FieldActionKind::Reject => {
                        Err(Fault::validation_at(FaultCode::UnknownField, at))
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

    fn scalar_field(
        &mut self,
        key: StringToken<'_>,
        token: ScalarToken<'_>,
        at: Position,
    ) -> Result<(), Fault> {
        if self.any_sub.is_some() {
            self.key(key, at)?;
            return self.scalar(token, at);
        }
        if self.skip_depth > 0 {
            return Ok(());
        }

        let strict = self.strict;
        let target = match self.stack.last_mut() {
            Some(Frame::Struct { plan, values, .. }) => {
                let action = Self::lookup_field_action(plan, self.row_memos.last_mut(), key);
                match action.kind() {
                    FieldActionKind::Tag | FieldActionKind::Skip => None,
                    FieldActionKind::Field => {
                        let index = action.field_index();
                        if values[index].is_some() && strict {
                            return Err(Fault::validation_at(FaultCode::DuplicateKey, at));
                        }
                        Some((index, plan.fields[index].value))
                    }
                    FieldActionKind::Reject => {
                        return Err(Fault::validation_at(FaultCode::UnknownField, at));
                    }
                }
            }
            _ => {
                self.key(key, at)?;
                return self.scalar(token, at);
            }
        };

        let Some((index, value_plan)) = target else {
            return Ok(());
        };
        let value = self.convert_scalar(value_plan, token, at)?;
        match self.stack.last_mut() {
            Some(Frame::Struct { values, .. }) => {
                values[index] = Some(value);
                Ok(())
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn end_object(&mut self, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::EndObject, at)?;
            debug_assert!(consumed);
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
            Some(Frame::ArrayStruct { .. }) => Err(Fault::syntax_at(FaultCode::Internal, at)),
            Some(Frame::Dict {
                map, constraints, ..
            }) => {
                Self::validate_length(constraints, map.len(), at)?;
                self.place(map.into_any(), at)
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn start_array(&mut self, declared_len: usize, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::StartArray(declared_len), at)?;
            debug_assert!(consumed);
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
            .root
            .resolve_container(self.expected_plan_or_fault(at)?);
        let expected_node = self.root.node(expected);
        match &expected_node.kind {
            PlanKind::List(item) => {
                let item_index = *item;
                let item = SequencePlan::Uniform(item_index);
                let mut memo = RowMemo::for_sequence(&item);
                if EXTENDED
                    && matches!(
                        &self.root.node(item_index).kind,
                        PlanKind::Union(union) if union.members.len() > 1
                    )
                {
                    memo.disabled = true;
                }
                self.row_memos.push(memo);
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(reserve_elements(declared_len)),
                    item,
                    as_tuple: false,
                    constraints: expected_node.constraints.as_deref(),
                });
                Ok(())
            }
            PlanKind::TupleVar(item) => {
                let item_index = *item;
                let item = SequencePlan::Uniform(item_index);
                let mut memo = RowMemo::for_sequence(&item);
                if EXTENDED
                    && matches!(
                        &self.root.node(item_index).kind,
                        PlanKind::Union(union) if union.members.len() > 1
                    )
                {
                    memo.disabled = true;
                }
                self.row_memos.push(memo);
                self.stack.push(Frame::List {
                    items: Vec::with_capacity(reserve_elements(declared_len)),
                    item,
                    as_tuple: true,
                    constraints: expected_node.constraints.as_deref(),
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
                    constraints: expected_node.constraints.as_deref(),
                });
                Ok(())
            }
            PlanKind::Struct(plan) if plan.array_like => {
                let mut values = self.values_pool.pop().unwrap_or_default();
                values.clear();
                values.resize(plan.fields.len(), None);
                self.stack.push(Frame::ArrayStruct {
                    plan,
                    values,
                    next: 0,
                    tag_pending: plan.tag_value.is_some(),
                });
                Ok(())
            }
            PlanKind::Union(union)
                if EXTENDED
                    && union.members.len() > 1
                    && union.members.iter().all(|&member| {
                        matches!(
                            &self.root.node(member).kind,
                            PlanKind::Struct(plan)
                                if plan.array_like && plan.tag_value.is_some()
                        )
                    }) =>
            {
                self.stack.push(Frame::ArrayStructUnion {
                    members: &union.members,
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
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::EndArray, at)?;
            debug_assert!(consumed);
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
                constraints,
            }) => {
                self.row_memos.pop();
                if item.expected_length().is_some_and(|len| items.len() != len) {
                    return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
                }
                Self::validate_length(constraints, items.len(), at)?;
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
            Some(Frame::ArrayStruct {
                plan,
                values,
                tag_pending: false,
                ..
            }) => {
                let value = self.finish_struct(plan, values, at)?;
                self.place(value, at)
            }
            Some(Frame::ArrayStruct { .. } | Frame::ArrayStructUnion { .. }) => {
                Err(Fault::validation_at(FaultCode::TypeMismatch, at))
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault> {
        if self.any_sub.is_some() {
            let consumed = self.any_forward(AnyEvent::Scalar(token), at)?;
            debug_assert!(consumed);
            return Ok(());
        }
        if self.skip_depth > 0 {
            return Ok(());
        }
        if self.top_struct_skips() {
            self.clear_top_skip();
            return Ok(());
        }
        if EXTENDED && self.has_array_tags && self.consume_array_tag(token, at)? {
            return Ok(());
        }
        let expected = self.expected_plan_or_fault(at)?;
        let value = self.convert_scalar(expected, token, at)?;
        self.place(value, at)
    }
}
