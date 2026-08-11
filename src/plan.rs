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
    List(usize),
    TupleVar(usize),
    /// `tuple[A, B, C]`: one plan per position, and the length is part of the
    /// type rather than a property of the document.
    TupleFixed(Vec<usize>),
    Dict(usize, usize),
    Struct(Box<StructPlan>),
    Union(Box<UnionPlan>),
    Literal(Vec<Py<PyAny>>),
    NativeScalar(Py<PyAny>),
    Custom(Py<PyAny>),
}

pub struct CompiledPlan {
    pub nodes: Vec<PlanNode>,
    pub root: usize,
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
    pub by_wire: FxHashMap<Vec<u8>, usize>,
    pub forbid_unknown: bool,
    pub array_like: bool,
    pub tag_field: Option<Vec<u8>>,
    pub tag_value: Option<TagValue>,
    /// Present when the class must be constructed with keyword arguments: the
    /// field names in constructor order, ready to hand to a vectorcall. The
    /// ordinary case keeps `None` and the positional fast path.
    pub keyword_names: Option<Py<pyo3::types::PyTuple>>,
}

pub enum TagValue {
    String(Vec<u8>),
    Integer(i64),
}

pub struct FieldPlan {
    pub python_name: Py<PyString>,
    pub wire_name: Vec<u8>,
    pub value: usize,
    pub default: DefaultPlan,
}

pub enum DefaultPlan {
    Required,
    Value(Py<PyAny>),
    Factory(Py<PyAny>),
}

pub struct UnionPlan {
    pub nullable: bool,
    pub members: Vec<usize>,
}

impl CompiledPlan {
    pub fn from_python(py: Python<'_>, spec: &Bound<'_, PyAny>) -> PyResult<Self> {
        let unset = py
            .import("msgspec_toon._types")?
            .getattr("_UNSET")?
            .unbind();
        let root = spec.getattr("root")?.extract::<usize>()?;
        let specs = spec.getattr("nodes")?;
        let node_count = specs.len()?;
        if root >= node_count || node_count > 4096 {
            return Err(PyValueError::new_err("invalid plan graph bounds"));
        }
        let mut nodes = Vec::with_capacity(node_count);
        for node in specs.try_iter()? {
            nodes.push(Self::lower_node(py, &node?, &specs, &unset, node_count)?);
        }
        Ok(Self { nodes, root })
    }

    fn edge(spec: &Bound<'_, PyAny>, name: &str, node_count: usize) -> PyResult<usize> {
        let edge = spec.getattr(name)?.extract::<usize>()?;
        if edge >= node_count {
            return Err(PyValueError::new_err("plan graph edge is out of bounds"));
        }
        Ok(edge)
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
                    let edge = item?.extract::<usize>()?;
                    if edge >= node_count {
                        return Err(PyValueError::new_err("plan graph edge is out of bounds"));
                    }
                    plans.push(edge);
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
                    let edge = member?.extract::<usize>()?;
                    if edge >= node_count {
                        return Err(PyValueError::new_err("plan graph edge is out of bounds"));
                    }
                    let member = graph_nodes.get_item(edge)?;
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
                    let value = field.getattr("plan")?.extract::<usize>()?;
                    if value >= node_count {
                        return Err(PyValueError::new_err("plan graph edge is out of bounds"));
                    }
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
                    by_wire.insert(wire_name.clone(), fields.len());
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
                    by_wire.insert(tag_field.clone(), usize::MAX);
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
    pub fn resolve_container(&self, mut index: usize) -> usize {
        for _ in 0..=self.nodes.len() {
            if let PlanKind::Union(union) = &self.nodes[index].kind
                && union.members.len() == 1
            {
                index = union.members[0];
                continue;
            }
            return index;
        }
        self.root
    }

    #[inline(always)]
    pub fn node(&self, index: usize) -> &PlanNode {
        // Every edge is range-checked once while the immutable arena is
        // compiled. Runtime node IDs originate only from those checked edges.
        unsafe { self.nodes.get_unchecked(index) }
    }

    pub fn requires_extended_consumer(&self) -> bool {
        self.nodes.iter().any(|node| match &node.kind {
            PlanKind::Struct(plan) => plan.array_like || plan.tag_field.is_some(),
            PlanKind::Union(union) => union.members.len() > 1,
            _ => false,
        })
    }
}
