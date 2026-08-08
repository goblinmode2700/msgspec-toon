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
    List(Box<CompiledPlan>),
    TupleVar(Box<CompiledPlan>),
    /// `tuple[A, B, C]`: one plan per position, and the length is part of the
    /// type rather than a property of the document.
    TupleFixed(Vec<CompiledPlan>),
    Dict(Box<CompiledPlan>, Box<CompiledPlan>),
    Struct(Box<StructPlan>),
    Union(Box<UnionPlan>),
    Literal(Vec<Py<PyAny>>),
    Custom(Py<PyAny>),
}

pub struct CompiledPlan {
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
    /// Present when the class must be constructed with keyword arguments: the
    /// field names in constructor order, ready to hand to a vectorcall. The
    /// ordinary case keeps `None` and the positional fast path.
    pub keyword_names: Option<Py<pyo3::types::PyTuple>>,
}

pub struct FieldPlan {
    pub python_name: Py<PyString>,
    pub wire_name: Vec<u8>,
    pub value: CompiledPlan,
    pub default: DefaultPlan,
}

pub enum DefaultPlan {
    Required,
    Value(Py<PyAny>),
    Factory(Py<PyAny>),
}

pub struct UnionPlan {
    pub nullable: bool,
    pub members: Vec<CompiledPlan>,
}

impl CompiledPlan {
    pub fn from_python(py: Python<'_>, spec: &Bound<'_, PyAny>) -> PyResult<Self> {
        let unset = py
            .import("msgspec_toon._types")?
            .getattr("_UNSET")?
            .unbind();
        Self::lower(py, spec, &unset)
    }

    fn lower(py: Python<'_>, spec: &Bound<'_, PyAny>, unset: &Py<PyAny>) -> PyResult<Self> {
        let kind_obj = spec.getattr("kind")?;
        let kind_text = kind_obj.extract::<&str>()?;
        let kind = match kind_text {
            "any" => PlanKind::Any,
            "none" => PlanKind::NoneT,
            "bool" => PlanKind::Bool,
            "int" => PlanKind::Int,
            "float" => PlanKind::Float,
            "str" => PlanKind::Str,
            "list" => {
                let item = Self::lower(py, &spec.getattr("item")?, unset)?;
                PlanKind::List(Box::new(item))
            }
            "tuple_var" => {
                let item = Self::lower(py, &spec.getattr("item")?, unset)?;
                PlanKind::TupleVar(Box::new(item))
            }
            "tuple_fixed" => {
                let mut plans = Vec::new();
                for item in spec.getattr("items")?.try_iter()? {
                    plans.push(Self::lower(py, &item?, unset)?);
                }
                PlanKind::TupleFixed(plans)
            }
            "dict" => {
                let key = Self::lower(py, &spec.getattr("key")?, unset)?;
                let value = Self::lower(py, &spec.getattr("value")?, unset)?;
                PlanKind::Dict(Box::new(key), Box::new(value))
            }
            "union" => {
                let mut nullable = false;
                let mut members = Vec::new();
                for member in spec.getattr("items")?.try_iter()? {
                    let member = member?;
                    if member.getattr("kind")?.extract::<&str>()? == "none" {
                        nullable = true;
                    } else {
                        members.push(Self::lower(py, &member, unset)?);
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
                    let value = Self::lower(py, &field.getattr("plan")?, unset)?;
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
                    keyword_names,
                }))
            }
            _ => {
                let class = spec.getattr("python_type")?.unbind();
                PlanKind::Custom(class)
            }
        };
        let constraints = Constraints::from_python(spec)?;
        Ok(Self { kind, constraints })
    }

    /// Unwrap `Optional[T]`-shaped unions to their single non-none member.
    pub fn resolve_container(&self) -> &CompiledPlan {
        if let PlanKind::Union(union) = &self.kind
            && union.members.len() == 1
        {
            return &union.members[0];
        }
        self
    }
}
