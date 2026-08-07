//! The canonical encoder (canvas AD-004, §11).
//!
//! Walks Python values directly. `msgspec.Struct` instances are read through
//! a cached per-class encode plan and attribute access — never
//! `msgspec.to_builtins`. Arrays of same-shaped objects emit tabular form
//! with nested field groups; anything else falls back exactly as the
//! specification directs.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

use crate::event::ScalarToken;
use crate::scalar::classify_bare;
use crate::writer::Writer;

const MAX_HOOK_DEPTH: usize = 8;
const MAX_ENCODE_DEPTH: usize = 256;

pub struct EncodeContext {
    pub enc_hook: Option<Py<PyAny>>,
    pub struct_base: Py<PyAny>,
    pub plan_source: Py<PyAny>,
    pub encode_error: Py<PyAny>,
    pub cache: Mutex<HashMap<usize, Arc<EncodePlan>>>,
}

pub struct EncodePlan {
    /// Pins the class so the pointer cache key cannot be reused.
    #[allow(dead_code)]
    class: Py<PyAny>,
    fields: Vec<EncodeField>,
    /// Precomputed tabular shape when the class's type plan proves every
    /// field is a primitive leaf or a (recursively static) nested Struct —
    /// rows of such a class need no runtime column scan at all.
    static_shape: Option<Arc<Vec<ShapeNode>>>,
}

struct EncodeField {
    attr: Py<PyString>,
    wire: String,
}

enum Val<'py> {
    None,
    Bool(bool),
    Int(Bound<'py, PyAny>),
    Float(f64),
    Str(Bound<'py, PyString>),
    Seq(Vec<Bound<'py, PyAny>>),
    Dict(Bound<'py, PyDict>),
    Struct(Bound<'py, PyAny>, Arc<EncodePlan>),
}

impl Val<'_> {
    fn is_scalar(&self) -> bool {
        matches!(
            self,
            Val::None | Val::Bool(_) | Val::Int(_) | Val::Float(_) | Val::Str(_)
        )
    }
}

fn encode_err(ctx: &EncodeContext, py: Python<'_>, message: &str) -> PyErr {
    match ctx.encode_error.bind(py).call1((message,)) {
        Ok(instance) => PyErr::from_value(instance),
        Err(err) => err,
    }
}

fn plan_for(
    ctx: &EncodeContext,
    py: Python<'_>,
    class: &Bound<'_, PyAny>,
) -> PyResult<Arc<EncodePlan>> {
    let key = class.as_ptr() as usize;
    if let Some(plan) = ctx.cache.lock().unwrap().get(&key) {
        return Ok(plan.clone());
    }
    let spec = ctx.plan_source.bind(py).call1((class,))?;
    let plan = plan_from_spec(ctx, py, class, &spec)?;
    ctx.cache.lock().unwrap().insert(key, plan.clone());
    Ok(plan)
}

/// Is a field's declared type always a tabular leaf (a primitive or an
/// optional/union of primitives)?
fn spec_is_leaf(spec: &Bound<'_, PyAny>) -> PyResult<bool> {
    let kind = spec.getattr("kind")?.extract::<String>()?;
    match kind.as_str() {
        "none" | "bool" | "int" | "float" | "str" => Ok(true),
        "union" => {
            for member in spec.getattr("items")?.try_iter()? {
                if !spec_is_leaf(&member?)? {
                    return Ok(false);
                }
            }
            Ok(true)
        }
        _ => Ok(false),
    }
}

fn plan_from_spec(
    ctx: &EncodeContext,
    py: Python<'_>,
    class: &Bound<'_, PyAny>,
    spec: &Bound<'_, PyAny>,
) -> PyResult<Arc<EncodePlan>> {
    let mut fields = Vec::new();
    let mut shape: Option<Vec<ShapeNode>> = Some(Vec::new());
    for field in spec.getattr("fields")?.try_iter()? {
        let field = field?;
        let name_text = field.getattr("python_name")?.extract::<String>()?;
        let attr = PyString::intern(py, &name_text).unbind();
        let wire = field.getattr("wire_name")?.extract::<String>()?;
        let value_spec = field.getattr("plan")?;

        if let Some(nodes) = shape.as_mut() {
            let kind = value_spec.getattr("kind")?.extract::<String>()?;
            if kind == "struct" {
                let nested_class = value_spec.getattr("python_type")?;
                let nested = plan_for_nested(ctx, py, &nested_class, &value_spec)?;
                match &nested.static_shape {
                    Some(children) => nodes.push(ShapeNode {
                        wire: wire.clone(),
                        access: Access::Attr(attr.clone_ref(py)),
                        children: clone_nodes(py, children),
                    }),
                    None => shape = None,
                }
            } else if spec_is_leaf(&value_spec)? {
                nodes.push(ShapeNode {
                    wire: wire.clone(),
                    access: Access::Attr(attr.clone_ref(py)),
                    children: Vec::new(),
                });
            } else {
                shape = None;
            }
        }

        fields.push(EncodeField { attr, wire });
    }
    let static_shape = match shape {
        Some(nodes) if !nodes.is_empty() => Some(Arc::new(nodes)),
        _ => None,
    };
    Ok(Arc::new(EncodePlan {
        class: class.clone().unbind(),
        fields,
        static_shape,
    }))
}

fn plan_for_nested(
    ctx: &EncodeContext,
    py: Python<'_>,
    class: &Bound<'_, PyAny>,
    spec: &Bound<'_, PyAny>,
) -> PyResult<Arc<EncodePlan>> {
    let key = class.as_ptr() as usize;
    if let Some(plan) = ctx.cache.lock().unwrap().get(&key) {
        return Ok(plan.clone());
    }
    let plan = plan_from_spec(ctx, py, class, spec)?;
    ctx.cache.lock().unwrap().insert(key, plan.clone());
    Ok(plan)
}

fn clone_nodes(py: Python<'_>, nodes: &[ShapeNode]) -> Vec<ShapeNode> {
    nodes
        .iter()
        .map(|node| ShapeNode {
            wire: node.wire.clone(),
            access: match &node.access {
                Access::Attr(attr) => Access::Attr(attr.clone_ref(py)),
                Access::Item(key) => Access::Item(key.clone_ref(py)),
            },
            children: clone_nodes(py, &node.children),
        })
        .collect()
}

fn classify<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    hook_depth: usize,
) -> PyResult<Val<'py>> {
    if obj.is_none() {
        return Ok(Val::None);
    }
    if obj.is_instance_of::<PyBool>() {
        return Ok(Val::Bool(obj.extract::<bool>()?));
    }
    if obj.is_instance_of::<PyInt>() {
        return Ok(Val::Int(obj.clone()));
    }
    if obj.is_instance_of::<PyFloat>() {
        let value = obj.extract::<f64>()?;
        if !value.is_finite() {
            return Err(encode_err(
                ctx,
                py,
                "non-finite floats are not encodable in TOON",
            ));
        }
        return Ok(Val::Float(value));
    }
    if let Ok(text) = obj.cast::<PyString>() {
        return Ok(Val::Str(text.clone()));
    }
    if obj.is_instance(ctx.struct_base.bind(py))? {
        let class = obj.get_type().into_any();
        let plan = plan_for(ctx, py, &class)?;
        return Ok(Val::Struct(obj.clone(), plan));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        return Ok(Val::Seq(list.iter().collect()));
    }
    if let Ok(tuple) = obj.cast::<PyTuple>() {
        return Ok(Val::Seq(tuple.iter().collect()));
    }
    if let Ok(map) = obj.cast::<PyDict>() {
        return Ok(Val::Dict(map.clone()));
    }
    if let Some(hook) = ctx.enc_hook.as_ref() {
        if hook_depth >= MAX_HOOK_DEPTH {
            return Err(encode_err(ctx, py, "enc_hook recursion limit exceeded"));
        }
        let replaced = hook.bind(py).call1((obj,))?;
        return classify(ctx, py, &replaced, hook_depth + 1);
    }
    let type_name = obj.get_type().name()?.to_string();
    Err(encode_err(
        ctx,
        py,
        &format!("unsupported type: {type_name}"),
    ))
}

fn object_pairs<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    value: &Val<'py>,
) -> PyResult<Vec<(String, Bound<'py, PyAny>)>> {
    match value {
        Val::Dict(map) => {
            let mut pairs = Vec::with_capacity(map.len());
            for (key, item) in map.iter() {
                let Ok(key_text) = key.cast::<PyString>() else {
                    return Err(encode_err(ctx, py, "object keys must be strings"));
                };
                pairs.push((key_text.to_str()?.to_string(), item));
            }
            Ok(pairs)
        }
        Val::Struct(instance, plan) => {
            let mut pairs = Vec::with_capacity(plan.fields.len());
            for field in &plan.fields {
                let item = instance.getattr(field.attr.bind(py))?;
                pairs.push((field.wire.clone(), item));
            }
            Ok(pairs)
        }
        _ => Err(encode_err(ctx, py, "not an object")),
    }
}

pub fn encode_root(
    ctx: &EncodeContext,
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Vec<u8>> {
    let mut writer = Writer::with_capacity(256);
    let value = classify(ctx, py, obj, 0)?;
    match &value {
        Val::Dict(_) | Val::Struct(_, _) => {
            let pairs = object_pairs(ctx, py, &value)?;
            write_entries(ctx, py, &mut writer, &pairs, 0)?;
        }
        Val::Seq(items) => write_array(ctx, py, &mut writer, None, items, 0, 0)?,
        _ => {
            write_scalar(ctx, py, &mut writer, &value)?;
            writer.newline();
        }
    }
    Ok(writer.finish())
}

fn write_entries<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    pairs: &[(String, Bound<'py, PyAny>)],
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_ENCODE_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
    for (key, item) in pairs {
        let value = classify(ctx, py, item, 0)?;
        match &value {
            Val::Seq(items) => {
                write_array(ctx, py, writer, Some(key), items, depth, 0)?;
            }
            Val::Dict(_) | Val::Struct(_, _) => {
                let nested = object_pairs(ctx, py, &value)?;
                writer.indent(depth);
                write_key(writer, key);
                writer.byte(b':');
                writer.newline();
                write_entries(ctx, py, writer, &nested, depth + 1)?;
            }
            _ => {
                writer.indent(depth);
                write_key(writer, key);
                writer.bytes(b": ");
                write_scalar(ctx, py, writer, &value)?;
                writer.newline();
            }
        }
    }
    Ok(())
}

fn write_array<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    key: Option<&str>,
    items: &[Bound<'py, PyAny>],
    depth: usize,
    nesting: usize,
) -> PyResult<()> {
    if nesting > MAX_ENCODE_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
    let header = |writer: &mut Writer, suffix: &str| {
        writer.indent(depth);
        if let Some(key) = key {
            write_key(writer, key);
        }
        writer.byte(b'[');
        let mut count = itoa::Buffer::new();
        writer.text(count.format(items.len()));
        writer.byte(b']');
        writer.text(suffix);
    };

    if items.is_empty() {
        header(writer, ":");
        writer.newline();
        return Ok(());
    }

    if items.iter().all(is_scalar_obj) {
        header(writer, ": ");
        for (index, item) in items.iter().enumerate() {
            if index > 0 {
                writer.byte(b',');
            }
            write_scalar_obj(ctx, py, writer, item)?;
        }
        writer.newline();
        return Ok(());
    }

    if let Some(shape) = build_shape(ctx, py, items)? {
        let nodes = shape.nodes();
        writer.indent(depth);
        if let Some(key) = key {
            write_key(writer, key);
        }
        writer.byte(b'[');
        let mut count = itoa::Buffer::new();
        writer.text(count.format(items.len()));
        writer.text("]{");
        write_field_group(writer, nodes);
        writer.text("}:");
        writer.newline();
        for item in items {
            writer.indent(depth + 1);
            let mut first = true;
            write_row_obj(ctx, py, writer, item, nodes, &mut first)?;
            writer.newline();
        }
        return Ok(());
    }

    // List fallback: `- ` items.
    header(writer, ":");
    writer.newline();
    for item in items {
        let value = classify(ctx, py, item, 0)?;
        write_list_item(ctx, py, writer, &value, depth + 1, nesting)?;
    }
    Ok(())
}

fn write_list_item<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    value: &Val<'py>,
    depth: usize,
    _nesting: usize,
) -> PyResult<()> {
    match value {
        Val::Dict(_) | Val::Struct(_, _) => {
            let pairs = object_pairs(ctx, py, value)?;
            if pairs.is_empty() {
                writer.indent(depth);
                writer.byte(b'-');
                writer.newline();
                return Ok(());
            }
            writer.indent(depth);
            writer.bytes(b"- ");
            let (first_key, first_item) = &pairs[0];
            let first_value = classify(ctx, py, first_item, 0)?;
            match &first_value {
                Val::Seq(seq) => {
                    let all_scalar_texts = inline_cells(ctx, py, seq)?;
                    match all_scalar_texts {
                        Some(cells) => {
                            write_key(writer, first_key);
                            writer.byte(b'[');
                            writer.text(&seq.len().to_string());
                            writer.bytes(b"]:");
                            if !cells.is_empty() {
                                writer.byte(b' ');
                                writer.text(&cells.join(","));
                            }
                            writer.newline();
                        }
                        None => {
                            return Err(encode_err(
                                ctx,
                                py,
                                "non-scalar arrays as the first field of a list item are not \
                                 supported by this proof of concept",
                            ));
                        }
                    }
                }
                Val::Dict(_) | Val::Struct(_, _) => {
                    let nested = object_pairs(ctx, py, &first_value)?;
                    write_key(writer, first_key);
                    writer.byte(b':');
                    writer.newline();
                    write_entries(ctx, py, writer, &nested, depth + 2)?;
                }
                _ => {
                    write_key(writer, first_key);
                    writer.bytes(b": ");
                    write_scalar(ctx, py, writer, &first_value)?;
                    writer.newline();
                }
            }
            write_entries(ctx, py, writer, &pairs[1..], depth + 1)?;
            Ok(())
        }
        Val::Seq(seq) => match inline_cells(ctx, py, seq)? {
            Some(cells) => {
                writer.indent(depth);
                writer.bytes(b"- [");
                writer.text(&seq.len().to_string());
                writer.bytes(b"]:");
                if !cells.is_empty() {
                    writer.byte(b' ');
                    writer.text(&cells.join(","));
                }
                writer.newline();
                Ok(())
            }
            None => Err(encode_err(
                ctx,
                py,
                "nested non-scalar arrays inside list items are not supported by this \
                     proof of concept",
            )),
        },
        _ => {
            writer.indent(depth);
            writer.bytes(b"- ");
            write_scalar(ctx, py, writer, value)?;
            writer.newline();
            Ok(())
        }
    }
}

fn inline_cells<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    items: &[Bound<'py, PyAny>],
) -> PyResult<Option<Vec<String>>> {
    let mut cells = Vec::with_capacity(items.len());
    for item in items {
        let value = classify(ctx, py, item, 0)?;
        if !value.is_scalar() {
            return Ok(None);
        }
        cells.push(scalar_text(ctx, py, &value)?);
    }
    Ok(Some(cells))
}

// --- tabular shape -----------------------------------------------------------

struct ShapeNode {
    wire: String,
    access: Access,
    children: Vec<ShapeNode>,
}

enum Access {
    Attr(Py<PyString>),
    Item(Py<PyAny>),
}

/// A row shape, either computed for this call or shared from a plan's
/// precomputed static shape.
enum Shape {
    Owned(Vec<ShapeNode>),
    Shared(Arc<Vec<ShapeNode>>),
}

impl Shape {
    fn nodes(&self) -> &[ShapeNode] {
        match self {
            Self::Owned(nodes) => nodes,
            Self::Shared(nodes) => nodes,
        }
    }
}

/// Fast scalar-primitive check that never touches the plan cache.
fn is_scalar_obj(obj: &Bound<'_, PyAny>) -> bool {
    obj.is_none()
        || obj.is_instance_of::<PyBool>()
        || obj.is_instance_of::<PyInt>()
        || obj.is_instance_of::<PyFloat>()
        || obj.is_instance_of::<PyString>()
}

/// Classify a row array once. All rows must share one shape — the same
/// Struct class or the same ordered dict keys — with every leaf a primitive
/// and every nested column uniformly object-shaped. Anything else bails to
/// the specification's list fallback.
fn build_shape<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    rows: &[Bound<'py, PyAny>],
) -> PyResult<Option<Shape>> {
    let first = &rows[0];
    let accessors: Vec<(String, Access)> = if first.is_instance(ctx.struct_base.bind(py))? {
        let class = first.get_type();
        if !rows.iter().skip(1).all(|row| row.get_type().is(&class)) {
            return Ok(None);
        }
        let plan = plan_for(ctx, py, class.as_any())?;
        if let Some(static_nodes) = &plan.static_shape {
            return Ok(Some(Shape::Shared(static_nodes.clone())));
        }
        plan.fields
            .iter()
            .map(|field| (field.wire.clone(), Access::Attr(field.attr.clone_ref(py))))
            .collect()
    } else if let Ok(first_map) = first.cast::<PyDict>() {
        let mut first_keys = Vec::with_capacity(first_map.len());
        for key in first_map.keys() {
            let Ok(text) = key.cast::<PyString>() else {
                return Ok(None);
            };
            first_keys.push(text.to_str()?.to_string());
        }
        for row in rows.iter().skip(1) {
            let Ok(map) = row.cast::<PyDict>() else {
                return Ok(None);
            };
            if map.len() != first_keys.len() {
                return Ok(None);
            }
            for (key, expected) in map.keys().iter().zip(&first_keys) {
                let Ok(text) = key.cast::<PyString>() else {
                    return Ok(None);
                };
                if text.to_str()? != expected {
                    return Ok(None);
                }
            }
        }
        first_keys
            .into_iter()
            .map(|key| {
                let key_obj = PyString::new(py, &key).into_any().unbind();
                (key, Access::Item(key_obj))
            })
            .collect()
    } else {
        return Ok(None);
    };

    if accessors.is_empty() {
        return Ok(None);
    }

    let mut shape = Vec::with_capacity(accessors.len());
    for (wire, access) in accessors {
        let mut column = Vec::with_capacity(rows.len());
        for row in rows {
            let item = match &access {
                Access::Attr(attr) => row.getattr(attr.bind(py))?,
                Access::Item(key) => match row.cast::<PyDict>() {
                    Ok(map) => match map.get_item(key.bind(py))? {
                        Some(item) => item,
                        None => return Ok(None),
                    },
                    Err(_) => return Ok(None),
                },
            };
            column.push(item);
        }
        if column.iter().all(is_scalar_obj) {
            shape.push(ShapeNode {
                wire,
                access,
                children: Vec::new(),
            });
        } else {
            match build_shape(ctx, py, &column)? {
                Some(nested) if !nested.nodes().is_empty() => {
                    let children = match nested {
                        Shape::Owned(nodes) => nodes,
                        Shape::Shared(nodes) => clone_nodes(py, &nodes),
                    };
                    shape.push(ShapeNode {
                        wire,
                        access,
                        children,
                    });
                }
                _ => return Ok(None),
            }
        }
    }
    Ok(Some(Shape::Owned(shape)))
}

fn write_field_group(writer: &mut Writer, shape: &[ShapeNode]) {
    for (index, node) in shape.iter().enumerate() {
        if index > 0 {
            writer.byte(b',');
        }
        write_key(writer, &node.wire);
        if !node.children.is_empty() {
            writer.byte(b'{');
            write_field_group(writer, &node.children);
            writer.byte(b'}');
        }
    }
}

/// Emit one row without re-classifying: the shape pass already proved every
/// leaf is a primitive and every group is object-shaped.
fn write_row_obj<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    row: &Bound<'py, PyAny>,
    shape: &[ShapeNode],
    first: &mut bool,
) -> PyResult<()> {
    for node in shape {
        let item = match &node.access {
            Access::Attr(attr) => row.getattr(attr.bind(py))?,
            Access::Item(key) => match row.cast::<PyDict>() {
                Ok(map) => map
                    .get_item(key.bind(py))?
                    .ok_or_else(|| encode_err(ctx, py, "row lost a classified column"))?,
                Err(_) => return Err(encode_err(ctx, py, "row lost its classified shape")),
            },
        };
        if node.children.is_empty() {
            if !*first {
                writer.byte(b',');
            }
            *first = false;
            write_scalar_obj(ctx, py, writer, &item)?;
        } else {
            write_row_obj(ctx, py, writer, &item, &node.children, first)?;
        }
    }
    Ok(())
}

// --- scalars -----------------------------------------------------------------

/// Write a scalar primitive straight into the output buffer, no intermediate
/// String except for the cold big-int and exponent-float paths.
fn write_scalar_obj<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    obj: &Bound<'py, PyAny>,
) -> PyResult<()> {
    if obj.is_none() {
        writer.bytes(b"null");
        return Ok(());
    }
    if obj.is_instance_of::<PyBool>() {
        writer.bytes(if obj.extract::<bool>()? {
            b"true"
        } else {
            b"false"
        });
        return Ok(());
    }
    if obj.is_instance_of::<PyInt>() {
        match obj.extract::<i64>() {
            Ok(small) => {
                let mut buffer = itoa::Buffer::new();
                writer.text(buffer.format(small));
            }
            Err(_) => writer.text(obj.str()?.to_str()?),
        }
        return Ok(());
    }
    if obj.is_instance_of::<PyFloat>() {
        let number = obj.extract::<f64>()?;
        if !number.is_finite() {
            return Err(encode_err(
                ctx,
                py,
                "non-finite floats are not encodable in TOON",
            ));
        }
        write_float(writer, number);
        return Ok(());
    }
    if let Ok(text) = obj.cast::<PyString>() {
        let text = text.to_str()?;
        if needs_quote(text) {
            write_quoted(writer, text);
        } else {
            writer.text(text);
        }
        return Ok(());
    }
    Err(encode_err(ctx, py, "value changed shape during encoding"))
}

fn write_float(writer: &mut Writer, number: f64) {
    if number == 0.0 {
        writer.byte(b'0');
        return;
    }
    if number.fract() == 0.0 && number.abs() < 1e16 {
        let mut buffer = itoa::Buffer::new();
        writer.text(buffer.format(number as i64));
        return;
    }
    let mut buffer = ryu::Buffer::new();
    let text = buffer.format_finite(number);
    match text.find('e') {
        Some(index) if text.as_bytes().get(index + 1) != Some(&b'-') => {
            writer.text(&text[..index]);
            writer.bytes(b"e+");
            writer.text(&text[index + 1..]);
        }
        _ => writer.text(text),
    }
}

fn write_quoted(writer: &mut Writer, text: &str) {
    writer.byte(b'"');
    for ch in text.chars() {
        match ch {
            '"' => writer.bytes(b"\\\""),
            '\\' => writer.bytes(b"\\\\"),
            '\n' => writer.bytes(b"\\n"),
            '\r' => writer.bytes(b"\\r"),
            '\t' => writer.bytes(b"\\t"),
            control if (control as u32) < 0x20 => {
                writer.text(&format!("\\u{:04x}", control as u32));
            }
            other => {
                let mut buf = [0u8; 4];
                writer.text(other.encode_utf8(&mut buf));
            }
        }
    }
    writer.byte(b'"');
}

fn write_scalar<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    value: &Val<'py>,
) -> PyResult<()> {
    let text = scalar_text(ctx, py, value)?;
    writer.text(&text);
    Ok(())
}

fn scalar_text<'py>(ctx: &EncodeContext, py: Python<'py>, value: &Val<'py>) -> PyResult<String> {
    match value {
        Val::None => Ok("null".to_string()),
        Val::Bool(true) => Ok("true".to_string()),
        Val::Bool(false) => Ok("false".to_string()),
        Val::Int(obj) => {
            if let Ok(small) = obj.extract::<i64>() {
                Ok(small.to_string())
            } else {
                Ok(obj.str()?.to_str()?.to_string())
            }
        }
        Val::Float(number) => Ok(canonical_float(*number)),
        Val::Str(text) => Ok(quote_if_needed(text.to_str()?)),
        _ => Err(encode_err(ctx, py, "not a scalar")),
    }
}

fn canonical_float(number: f64) -> String {
    if number == 0.0 {
        return "0".to_string();
    }
    if number.fract() == 0.0 && number.abs() < 1e16 {
        return format!("{}", number as i64);
    }
    let mut buffer = ryu::Buffer::new();
    let text = buffer.format_finite(number);
    // Match the canonical (JavaScript-style) positive exponent spelling.
    match text.find('e') {
        Some(index) if text.as_bytes().get(index + 1) != Some(&b'-') => {
            format!("{}e+{}", &text[..index], &text[index + 1..])
        }
        _ => text.to_string(),
    }
}

fn needs_quote(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return true;
    }
    if !matches!(classify_bare(bytes), ScalarToken::BareString(_)) {
        return true;
    }
    if bytes[0] == b' '
        || bytes[bytes.len() - 1] == b' '
        || matches!(bytes[0], b'"' | b'[' | b'{' | b'#' | b'\'')
    {
        return true;
    }
    if text == "-" || text.starts_with("- ") {
        return true;
    }
    bytes
        .iter()
        .any(|&byte| matches!(byte, b',' | b':' | b'\n' | b'\r' | b'\t') || byte < 0x20)
}

fn quote_if_needed(text: &str) -> String {
    if needs_quote(text) {
        quote(text)
    } else {
        text.to_string()
    }
}

fn quote(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            control if (control as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", control as u32));
            }
            other => out.push(other),
        }
    }
    out.push('"');
    out
}

fn key_needs_quote(text: &str) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return true;
    }
    if !(bytes[0].is_ascii_alphabetic() || bytes[0] == b'_') {
        return true;
    }
    !bytes
        .iter()
        .all(|&byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-' || byte == b'.')
}

fn write_key(writer: &mut Writer, key: &str) {
    if key_needs_quote(key) {
        writer.text(&quote(key));
    } else {
        writer.text(key);
    }
}

#[cfg(test)]
mod tests {
    use super::canonical_float;

    #[test]
    fn floats_are_canonical() {
        assert_eq!(canonical_float(0.0), "0");
        assert_eq!(canonical_float(-0.0), "0");
        assert_eq!(canonical_float(1.0), "1");
        assert_eq!(canonical_float(1.5), "1.5");
        assert_eq!(canonical_float(1e-7), "1e-7");
        assert_eq!(canonical_float(1e21), "1e+21");
    }
}
