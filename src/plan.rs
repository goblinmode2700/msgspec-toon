//! The compiled type plan: the Rust lowering of the frozen `PlanSpec` IR
//! produced by `msgspec_toon._plan`. Nothing here reads `msgspec.inspect`.

use rustc_hash::FxHashMap;

use pyo3::prelude::*;
use pyo3::types::PyString;

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
}

pub struct StructPlan {
    pub class: Py<PyAny>,
    pub fields: Vec<FieldPlan>,
    pub by_wire: FxHashMap<Vec<u8>, usize>,
    pub forbid_unknown: bool,
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
                PlanKind::Struct(Box::new(StructPlan {
                    class,
                    fields,
                    by_wire,
                    forbid_unknown,
                }))
            }
            _ => {
                let class = spec.getattr("python_type")?.unbind();
                PlanKind::Custom(class)
            }
        };
        Ok(Self { kind })
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
