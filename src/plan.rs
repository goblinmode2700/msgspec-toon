//! The compiled type plan: the Rust lowering of the frozen `PlanSpec` IR
//! produced by `msgspec_toon._plan`. Nothing here reads `msgspec.inspect`.

use rustc_hash::FxHashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyString, PyTuple};

pub enum PlanKind {
    Any,
    NoneT,
    Bool,
    Int,
    Float,
    Str,
    List(PlanId),
    TupleVar(PlanId),
    /// `tuple[A, B, C]`: one plan per position, and the length is part of the
    /// type rather than a property of the document.
    TupleFixed(Vec<PlanId>),
    Dict(PlanId, PlanId),
    Struct(Box<StructPlan>),
    Union(Box<UnionPlan>),
    Literal(Vec<Py<PyAny>>),
    NativeScalar(Py<PyAny>),
    Custom(Py<PyAny>),
}

/// A validated index into one immutable `CompiledPlan` arena.
///
/// Construction is confined to plan lowering. Runtime decode can therefore
/// distinguish arena identity from Struct field positions without changing
/// the machine-word representation used by the hot path.
#[repr(transparent)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct PlanId(usize);

impl PlanId {
    fn checked(index: usize, node_count: usize) -> PyResult<Self> {
        if index >= node_count {
            return Err(PyValueError::new_err("plan graph edge is out of bounds"));
        }
        Ok(Self(index))
    }

    #[inline(always)]
    pub(crate) fn index(self) -> usize {
        self.0
    }
}

pub struct CompiledPlan {
    pub nodes: Vec<PlanNode>,
    pub(crate) root: PlanId,
}

pub struct PlanNode {
    pub kind: PlanKind,
    /// `None` is the unconstrained fast path. Constraint-bearing annotations
    /// pay for Python comparisons or regex matching only after conversion.
    pub constraints: Option<Box<Constraints>>,
}

pub struct Constraints {
    pub ge: Option<Py<PyAny>>,
    pub gt: Option<Py<PyAny>>,
    pub le: Option<Py<PyAny>>,
    pub lt: Option<Py<PyAny>>,
    pub multiple_of: Option<Py<PyAny>>,
    pub min_length: Option<usize>,
    pub max_length: Option<usize>,
    pub pattern: Option<Py<PyAny>>,
}

impl Constraints {
    fn from_python(spec: &Bound<'_, PyAny>) -> PyResult<Option<Box<Self>>> {
        let mut constraints = Self {
            ge: None,
            gt: None,
            le: None,
            lt: None,
            multiple_of: None,
            min_length: None,
            max_length: None,
            pattern: None,
        };
        let mut any = false;
        for pair in spec.getattr("constraints")?.try_iter()? {
            let pair = pair?.cast_into::<PyTuple>()?;
            let name_obj = pair.get_item(0)?;
            let name = name_obj.extract::<&str>()?;
            let value = pair.get_item(1)?;
            any = true;
            match name {
                "ge" => constraints.ge = Some(value.unbind()),
                "gt" => constraints.gt = Some(value.unbind()),
                "le" => constraints.le = Some(value.unbind()),
                "lt" => constraints.lt = Some(value.unbind()),
                "multiple_of" => constraints.multiple_of = Some(value.unbind()),
                "min_length" => constraints.min_length = Some(value.extract::<usize>()?),
                "max_length" => constraints.max_length = Some(value.extract::<usize>()?),
                "pattern" => constraints.pattern = Some(value.unbind()),
                // `tz` belongs to datetime, which is still an unsupported
                // custom type. Silently dropping a new constraint name on a
                // supported plan would recreate C-00, so unknown names fail.
                "tz" => {}
                _ => {
                    return Err(PyValueError::new_err(
                        "unknown constraint in msgspec-toon plan IR",
                    ));
                }
            }
        }
        Ok(any.then(|| Box::new(constraints)))
    }

    pub fn length_valid(&self, length: usize) -> bool {
        self.min_length.is_none_or(|minimum| length >= minimum)
            && self.max_length.is_none_or(|maximum| length <= maximum)
    }

    pub fn scalar_valid(&self, value: &Bound<'_, PyAny>) -> PyResult<bool> {
        if let Some(bound) = &self.ge
            && !value.ge(bound.bind(value.py()))?
        {
            return Ok(false);
        }
        if let Some(bound) = &self.gt
            && !value.gt(bound.bind(value.py()))?
        {
            return Ok(false);
        }
        if let Some(bound) = &self.le
            && !value.le(bound.bind(value.py()))?
        {
            return Ok(false);
        }
        if let Some(bound) = &self.lt
            && !value.lt(bound.bind(value.py()))?
        {
            return Ok(false);
        }
        if let Some(divisor) = &self.multiple_of
            && !value.rem(divisor.bind(value.py()))?.eq(0)?
        {
            return Ok(false);
        }
        if (self.min_length.is_some() || self.max_length.is_some())
            && !self.length_valid(value.len()?)
        {
            return Ok(false);
        }
        if let Some(pattern) = &self.pattern
            && pattern
                .bind(value.py())
                .call_method1("search", (value,))?
                .is_none()
        {
            return Ok(false);
        }
        Ok(true)
    }
}

pub struct StructPlan {
    pub class: Py<PyAny>,
    pub fields: Vec<FieldPlan>,
    pub by_wire: FxHashMap<Vec<u8>, FieldAction>,
    pub forbid_unknown: bool,
    pub array_like: bool,
    pub tag_field: Option<Vec<u8>>,
    pub tag_value: Option<TagValue>,
    /// Present when the class must be constructed with keyword arguments: the
    /// field names in constructor order, ready to hand to a vectorcall. The
    /// ordinary case keeps `None` and the positional fast path.
    pub keyword_names: Option<Py<pyo3::types::PyTuple>>,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FieldActionKind {
    Field,
    Tag,
    Skip,
    Reject,
}

/// A compact closed action for one Struct wire key.
///
/// The field index is checked once while the plan is compiled. Keeping the
/// kind separate makes the four states explicit without doubling every hash
/// map and row-memo value to a two-word payload enum.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldAction {
    field_index: u32,
    kind: FieldActionKind,
}

impl FieldAction {
    const TAG: Self = Self::new(FieldActionKind::Tag);
    const SKIP: Self = Self::new(FieldActionKind::Skip);
    const REJECT: Self = Self::new(FieldActionKind::Reject);

    const fn new(kind: FieldActionKind) -> Self {
        Self {
            field_index: 0,
            kind,
        }
    }

    fn field(index: usize) -> PyResult<Self> {
        let field_index = u32::try_from(index)
            .map_err(|_| PyValueError::new_err("Struct plan has too many fields"))?;
        Ok(Self {
            field_index,
            kind: FieldActionKind::Field,
        })
    }

    #[inline]
    pub fn kind(self) -> FieldActionKind {
        self.kind
    }

    #[inline]
    pub fn field_index(self) -> usize {
        debug_assert_eq!(self.kind, FieldActionKind::Field);
        self.field_index as usize
    }
}

impl StructPlan {
    #[inline]
    pub fn field_action(&self, wire_name: &[u8]) -> FieldAction {
        self.by_wire
            .get(wire_name)
            .copied()
            .unwrap_or(if self.forbid_unknown {
                FieldAction::REJECT
            } else {
                FieldAction::SKIP
            })
    }
}

pub enum TagValue {
    String(Vec<u8>),
    Integer(i64),
}

pub struct FieldPlan {
    pub python_name: Py<PyString>,
    pub wire_name: Vec<u8>,
    pub(crate) value: PlanId,
    pub default: DefaultPlan,
}

pub enum DefaultPlan {
    Required,
    Value(Py<PyAny>),
    Factory(Py<PyAny>),
}

pub struct UnionPlan {
    pub nullable: bool,
    pub members: Vec<PlanId>,
}

impl CompiledPlan {
    pub fn from_python(py: Python<'_>, spec: &Bound<'_, PyAny>) -> PyResult<Self> {
        let unset = py
            .import("msgspec_toon._types")?
            .getattr("_UNSET")?
            .unbind();
        let root_index = spec.getattr("root")?.extract::<usize>()?;
        let specs = spec.getattr("nodes")?;
        let node_count = specs.len()?;
        if node_count > 4096 {
            return Err(PyValueError::new_err("invalid plan graph bounds"));
        }
        let root = PlanId::checked(root_index, node_count)?;
        let mut nodes = Vec::with_capacity(node_count);
        for node in specs.try_iter()? {
            nodes.push(Self::lower_node(py, &node?, &specs, &unset, node_count)?);
        }
        Self::validate_container_chains(&nodes)?;
        Ok(Self { nodes, root })
    }

    fn validate_container_chains(nodes: &[PlanNode]) -> PyResult<()> {
        for start in 0..nodes.len() {
            let mut id = PlanId(start);
            for step in 0..=nodes.len() {
                match &nodes[id.index()].kind {
                    PlanKind::Union(union) if union.members.len() == 1 => {
                        if step == nodes.len() {
                            return Err(PyValueError::new_err(
                                "plan graph has a cyclic container edge",
                            ));
                        }
                        id = union.members[0];
                    }
                    _ => break,
                }
            }
        }
        Ok(())
    }

    fn edge(spec: &Bound<'_, PyAny>, name: &str, node_count: usize) -> PyResult<PlanId> {
        PlanId::checked(spec.getattr(name)?.extract()?, node_count)
    }

    fn lower_node(
        py: Python<'_>,
        spec: &Bound<'_, PyAny>,
        graph_nodes: &Bound<'_, PyAny>,
        unset: &Py<PyAny>,
        node_count: usize,
    ) -> PyResult<PlanNode> {
        let kind_obj = spec.getattr("kind")?;
        let kind_text = kind_obj.extract::<&str>()?;
        let kind = match kind_text {
            "any" => PlanKind::Any,
            "none" => PlanKind::NoneT,
            "bool" => PlanKind::Bool,
            "int" => PlanKind::Int,
            "float" => PlanKind::Float,
            "str" => PlanKind::Str,
            "list" => PlanKind::List(Self::edge(spec, "item", node_count)?),
            "tuple_var" => PlanKind::TupleVar(Self::edge(spec, "item", node_count)?),
            "tuple_fixed" => {
                let mut plans = Vec::new();
                for item in spec.getattr("items")?.try_iter()? {
                    plans.push(PlanId::checked(item?.extract()?, node_count)?);
                }
                PlanKind::TupleFixed(plans)
            }
            "dict" => PlanKind::Dict(
                Self::edge(spec, "key", node_count)?,
                Self::edge(spec, "value", node_count)?,
            ),
            "union" => {
                let mut nullable = false;
                let mut members = Vec::new();
                for member in spec.getattr("items")?.try_iter()? {
                    let edge = PlanId::checked(member?.extract()?, node_count)?;
                    let member = graph_nodes.get_item(edge.index())?;
                    if member.getattr("kind")?.extract::<&str>()? == "none" {
                        nullable = true;
                    } else {
                        members.push(edge);
                    }
                }
                PlanKind::Union(Box::new(UnionPlan { nullable, members }))
            }
            "literal" => {
                let mut values = Vec::new();
                for value in spec.getattr("items")?.try_iter()? {
                    values.push(value?.unbind());
                }
                PlanKind::Literal(values)
            }
            "native_scalar" => {
                let class = spec.getattr("python_type")?.unbind();
                PlanKind::NativeScalar(class)
            }
            "struct" => {
                let class = spec.getattr("python_type")?.unbind();
                let mut fields = Vec::new();
                let mut by_wire = FxHashMap::default();
                for field in spec.getattr("fields")?.try_iter()? {
                    let field = field?;
                    let python_name = field
                        .getattr("python_name")?
                        .cast_into::<PyString>()?
                        .unbind();
                    let wire_name = field
                        .getattr("wire_name")?
                        .extract::<String>()?
                        .into_bytes();
                    let value = PlanId::checked(field.getattr("plan")?.extract()?, node_count)?;
                    let required = field.getattr("required")?.extract::<bool>()?;
                    let default_factory = field.getattr("default_factory")?;
                    let default_value = field.getattr("default")?;
                    let default = if required {
                        DefaultPlan::Required
                    } else if !default_factory.is_none() {
                        DefaultPlan::Factory(default_factory.unbind())
                    } else if default_value.is(unset.bind(py)) {
                        DefaultPlan::Required
                    } else {
                        DefaultPlan::Value(default_value.unbind())
                    };
                    by_wire.insert(wire_name.clone(), FieldAction::field(fields.len())?);
                    fields.push(FieldPlan {
                        python_name,
                        wire_name,
                        value,
                        default,
                    });
                }
                let forbid_unknown = spec.getattr("forbid_unknown_fields")?.extract::<bool>()?;
                let array_like = spec.getattr("array_like")?.extract::<bool>()?;
                let tag_field = spec
                    .getattr("tag_field")?
                    .extract::<Option<String>>()?
                    .map(String::into_bytes);
                let tag_value_obj = spec.getattr("tag_value")?;
                let tag_value = if tag_value_obj.is_none() {
                    None
                } else if let Ok(text) = tag_value_obj.cast::<PyString>() {
                    Some(TagValue::String(text.to_str()?.as_bytes().to_vec()))
                } else {
                    Some(TagValue::Integer(tag_value_obj.extract::<i64>()?))
                };
                if let Some(tag_field) = &tag_field {
                    by_wire.insert(tag_field.clone(), FieldAction::TAG);
                }
                let keyword_names = if spec.getattr("keyword_only")?.extract::<bool>()? {
                    let names = fields
                        .iter()
                        .map(|field| field.python_name.bind(py).clone().into_any())
                        .collect();
                    Some(crate::containers::new_plan_tuple(py, names)?.unbind())
                } else {
                    None
                };
                PlanKind::Struct(Box::new(StructPlan {
                    class,
                    fields,
                    by_wire,
                    forbid_unknown,
                    array_like,
                    tag_field,
                    tag_value,
                    keyword_names,
                }))
            }
            _ => {
                let class = spec.getattr("python_type")?.unbind();
                PlanKind::Custom(class)
            }
        };
        let constraints = Constraints::from_python(spec)?;
        Ok(PlanNode { kind, constraints })
    }

    /// Unwrap `Optional[T]`-shaped unions to their single non-none member.
    #[inline(always)]
    pub fn resolve_container(&self, mut id: PlanId) -> PlanId {
        for _ in 0..=self.nodes.len() {
            if let PlanKind::Union(union) = &self.node(id).kind
                && union.members.len() == 1
            {
                id = union.members[0];
                continue;
            }
            return id;
        }
        invalid_container_cycle()
    }

    #[inline(always)]
    pub(crate) fn node(&self, id: PlanId) -> &PlanNode {
        // SAFETY: every `PlanId` enters through checked plan compilation.
        // Recursive edges are range-checked there, and container-chain cycles
        // are rejected before the immutable arena becomes visible at runtime.
        unsafe { self.nodes.get_unchecked(id.index()) }
    }

    pub fn requires_extended_consumer(&self) -> bool {
        self.nodes.iter().any(|node| match &node.kind {
            PlanKind::Struct(plan) => plan.array_like || plan.tag_field.is_some(),
            PlanKind::Union(union) => union.members.len() > 1,
            _ => false,
        })
    }
}

#[cold]
#[inline(never)]
fn invalid_container_cycle() -> ! {
    unreachable!("container-plan cycles are rejected during plan compilation")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_id_is_one_checked_machine_word() {
        Python::initialize();
        assert_eq!(std::mem::size_of::<PlanId>(), std::mem::size_of::<usize>());
        assert_eq!(PlanId::checked(2, 3).unwrap().index(), 2);
        Python::attach(|py| {
            let err = PlanId::checked(3, 3).unwrap_err();
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    #[test]
    fn field_action_is_compact_and_checks_its_index() {
        Python::initialize();
        assert_eq!(std::mem::size_of::<FieldAction>(), 8);
        let action = FieldAction::field(7).unwrap();
        assert_eq!(action.kind(), FieldActionKind::Field);
        assert_eq!(action.field_index(), 7);
        Python::attach(|py| {
            let err = FieldAction::field(u32::MAX as usize + 1).unwrap_err();
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    #[test]
    fn cyclic_container_plan_is_rejected_before_decode() {
        Python::initialize();
        let nodes = vec![PlanNode {
            kind: PlanKind::Union(Box::new(UnionPlan {
                nullable: false,
                members: vec![PlanId(0)],
            })),
            constraints: None,
        }];
        Python::attach(|py| {
            let err = CompiledPlan::validate_container_chains(&nodes).unwrap_err();
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }
}
