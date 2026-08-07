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
use crate::limits::{MAX_NESTING_DEPTH, reserve_bytes};
use crate::scalar::classify_bare;
use crate::writer::Writer;

/// Capacity heuristic only — never policy: an assumed average encoded cell
/// width used to pre-reserve the output buffer for tabular rows.
const CELL_WIDTH_ESTIMATE: usize = 10;

const MAX_HOOK_DEPTH: usize = 8;

pub struct EncodeContext {
    pub enc_hook: Option<Py<PyAny>>,
    pub struct_base: Py<PyAny>,
    pub plan_source: Py<PyAny>,
    pub encode_error: Py<PyAny>,
    pub cache: Mutex<HashMap<usize, Arc<EncodePlan>>>,
    /// Spec-defined wire options (TOON 4.1 delimiter and indentation width);
    /// defaults produce canonical output.
    pub delimiter: u8,
    pub indent: usize,
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
    let mut writer = Writer::with_capacity(256, ctx.indent);
    let value = classify(ctx, py, obj, 0)?;
    match &value {
        Val::Dict(_) | Val::Struct(_, _) => {
            if let Some(keyed) = keyed_shape(ctx, py, &value, 0)? {
                write_keyed(ctx, py, &mut writer, None, &keyed, 0, false)?;
            } else {
                let pairs = object_pairs(ctx, py, &value)?;
                write_entries(ctx, py, &mut writer, &pairs, 0)?;
            }
        }
        Val::Seq(items) => write_array(ctx, py, &mut writer, None, items, 0, 0, false)?,
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
    if depth > MAX_NESTING_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
    for (key, item) in pairs {
        write_entry(ctx, py, writer, key, item, depth, false)?;
    }
    Ok(())
}

/// Write one `key: value` entry. With `inline`, the writer is already
/// positioned on the entry's line (after a `- ` prefix) and the first line
/// must not be indented again.
fn write_entry<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    key: &str,
    item: &Bound<'py, PyAny>,
    depth: usize,
    inline: bool,
) -> PyResult<()> {
    let value = classify(ctx, py, item, 0)?;
    match &value {
        Val::Seq(items) => write_array(ctx, py, writer, Some(key), items, depth, 0, inline),
        Val::Dict(_) | Val::Struct(_, _) => {
            if let Some(keyed) = keyed_shape(ctx, py, &value, depth)? {
                return write_keyed(ctx, py, writer, Some(key), &keyed, depth, inline);
            }
            let nested = object_pairs(ctx, py, &value)?;
            if !inline {
                writer.indent(depth);
            }
            write_key(writer, key);
            writer.byte(b':');
            writer.newline();
            write_entries(ctx, py, writer, &nested, depth + 1)
        }
        _ => {
            if !inline {
                writer.indent(depth);
            }
            write_key(writer, key);
            writer.bytes(b": ");
            write_scalar(ctx, py, writer, &value)?;
            writer.newline();
            Ok(())
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn write_array<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    key: Option<&str>,
    items: &[Bound<'py, PyAny>],
    depth: usize,
    nesting: usize,
    inline: bool,
) -> PyResult<()> {
    if nesting > MAX_NESTING_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
    let header = |writer: &mut Writer, suffix: &str| {
        if !inline {
            writer.indent(depth);
        }
        if let Some(key) = key {
            write_key(writer, key);
        }
        writer.byte(b'[');
        let mut count = itoa::Buffer::new();
        writer.text(count.format(items.len()));
        if ctx.delimiter != b',' {
            writer.byte(ctx.delimiter);
        }
        writer.byte(b']');
        writer.text(suffix);
    };

    if items.is_empty() {
        // Named values and the document root spell an empty array as the
        // literal `[]`; an anonymous empty array in list-item position keeps
        // the `[0]:` header form.
        if key.is_none() && inline {
            header(writer, ":");
            writer.newline();
            return Ok(());
        }
        if !inline {
            writer.indent(depth);
        }
        if let Some(key) = key {
            write_key(writer, key);
            writer.bytes(b": ");
        }
        writer.bytes(b"[]");
        writer.newline();
        return Ok(());
    }

    if items.iter().all(is_scalar_obj) {
        header(writer, ": ");
        for (index, item) in items.iter().enumerate() {
            if index > 0 {
                writer.byte(ctx.delimiter);
            }
            write_scalar_obj(ctx, py, writer, item)?;
        }
        writer.newline();
        return Ok(());
    }

    // Tabular form applies to named arrays and the root array; an anonymous
    // array in list-item position always uses list form.
    if (key.is_some() || !inline)
        && let Some(shape) = build_shape(ctx, py, items, nesting)?
    {
        let nodes = shape.nodes();
        if !inline {
            writer.indent(depth);
        }
        if let Some(key) = key {
            write_key(writer, key);
        }
        writer.byte(b'[');
        let mut count = itoa::Buffer::new();
        writer.text(count.format(items.len()));
        if ctx.delimiter != b',' {
            writer.byte(ctx.delimiter);
        }
        writer.text("]{");
        write_field_group(writer, nodes, ctx.delimiter);
        writer.text("}:");
        writer.newline();
        // Optimization E2: one up-front reservation instead of growth
        // doublings while streaming rows.
        let row_width_estimate =
            (depth + 1) * ctx.indent + shape_leaf_count(nodes) * CELL_WIDTH_ESTIMATE + 1;
        writer.reserve(reserve_bytes(
            items.len().saturating_mul(row_width_estimate),
        ));
        for item in items {
            writer.indent(depth + 1);
            let mut first = true;
            write_row_obj(ctx, py, writer, item, nodes, &mut first)?;
            writer.newline();
        }
        return Ok(());
    }

    // List fallback: `- ` items one level below the array construct.
    header(writer, ":");
    writer.newline();
    for item in items {
        write_list_item(ctx, py, writer, item, depth + 1, nesting + 1)?;
    }
    Ok(())
}

fn write_list_item<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    item: &Bound<'py, PyAny>,
    depth: usize,
    nesting: usize,
) -> PyResult<()> {
    let value = classify(ctx, py, item, 0)?;
    match &value {
        Val::Dict(_) | Val::Struct(_, _) => {
            let pairs = object_pairs(ctx, py, &value)?;
            if pairs.is_empty() {
                writer.indent(depth);
                writer.byte(b'-');
                writer.newline();
                return Ok(());
            }
            writer.indent(depth);
            writer.bytes(b"- ");
            let (first_key, first_item) = &pairs[0];
            // The item's fields live one level below the dash line; the
            // first field shares the dash line itself.
            write_entry(ctx, py, writer, first_key, first_item, depth + 1, true)?;
            write_entries(ctx, py, writer, &pairs[1..], depth + 1)?;
            Ok(())
        }
        Val::Seq(seq) => {
            // An anonymous nested array item: `- []`, `- [n]: cells`, or
            // block list form with its items one level below the dash line.
            writer.indent(depth);
            writer.bytes(b"- ");
            write_array(ctx, py, writer, None, seq, depth, nesting + 1, true)
        }
        _ => {
            writer.indent(depth);
            writer.bytes(b"- ");
            write_scalar(ctx, py, writer, &value)?;
            writer.newline();
            Ok(())
        }
    }
}

// --- keyed tabular form ------------------------------------------------------

/// An eligible keyed tabular object: two or more entries, every value an
/// object of one uniform shape. Field order follows the first entry.
struct KeyedShape<'py> {
    entries: Vec<(String, Bound<'py, PyAny>)>,
    shape: Shape,
}

fn keyed_shape<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    value: &Val<'py>,
    depth: usize,
) -> PyResult<Option<KeyedShape<'py>>> {
    let Val::Dict(map) = value else {
        return Ok(None);
    };
    if map.len() < 2 {
        return Ok(None);
    }
    let mut entries = Vec::with_capacity(map.len());
    let mut rows = Vec::with_capacity(map.len());
    for (key, item) in map.iter() {
        let Ok(key_text) = key.cast::<PyString>() else {
            return Ok(None);
        };
        if !(item.is_instance_of::<PyDict>() || item.is_instance(ctx.struct_base.bind(py))?) {
            return Ok(None);
        }
        entries.push((key_text.to_str()?.to_string(), item.clone()));
        rows.push(item);
    }
    let Some(shape) = build_shape(ctx, py, &rows, depth)? else {
        return Ok(None);
    };
    Ok(Some(KeyedShape { entries, shape }))
}

fn write_keyed<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    key: Option<&str>,
    keyed: &KeyedShape<'py>,
    depth: usize,
    inline: bool,
) -> PyResult<()> {
    let nodes = keyed.shape.nodes();
    if !inline {
        writer.indent(depth);
    }
    if let Some(key) = key {
        write_key(writer, key);
    }
    writer.byte(b'[');
    let mut count = itoa::Buffer::new();
    writer.text(count.format(keyed.entries.len()));
    writer.byte(b':');
    if ctx.delimiter != b',' {
        writer.byte(ctx.delimiter);
    }
    writer.text("]{");
    write_field_group(writer, nodes, ctx.delimiter);
    writer.text("}:");
    writer.newline();
    for (row_key, row) in &keyed.entries {
        writer.indent(depth + 1);
        write_key(writer, row_key);
        writer.bytes(b": ");
        let mut first = true;
        write_row_obj(ctx, py, writer, row, nodes, &mut first)?;
        writer.newline();
    }
    Ok(())
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
    let type_ptr = exact_type(obj);
    {
        use std::ptr::addr_of_mut;
        if type_ptr == addr_of_mut!(pyo3::ffi::PyUnicode_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyLong_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyFloat_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyBool_Type)
        {
            return true;
        }
    }
    obj.is_none()
        || obj.is_instance_of::<PyBool>()
        || obj.is_instance_of::<PyInt>()
        || obj.is_instance_of::<PyFloat>()
        || obj.is_instance_of::<PyString>()
}

/// Classify a row array once. All rows must share one shape — the same
/// Struct class or the same dict key set — with every leaf a primitive and
/// every nested column uniformly object-shaped. Anything else bails to the
/// specification's list fallback. Dict rows may list their keys in any
/// order; columns follow the first row's encounter order.
fn build_shape<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    rows: &[Bound<'py, PyAny>],
    depth: usize,
) -> PyResult<Option<Shape>> {
    // Shape discovery recurses per nested column, ahead of the writer's own
    // depth check, so it needs the same ceiling. Bailing to list form here
    // would only defer the error to the writer; report it directly.
    if depth > MAX_NESTING_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
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
            // Same key set is enough; the column pass fetches by name and
            // bails if any key is absent.
            for key in map.keys() {
                let Ok(text) = key.cast::<PyString>() else {
                    return Ok(None);
                };
                let text = text.to_str()?;
                if !first_keys.iter().any(|expected| expected == text) {
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
            match build_shape(ctx, py, &column, depth + 1)? {
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

fn shape_leaf_count(shape: &[ShapeNode]) -> usize {
    shape
        .iter()
        .map(|node| {
            if node.children.is_empty() {
                1
            } else {
                shape_leaf_count(&node.children)
            }
        })
        .sum()
}

fn write_field_group(writer: &mut Writer, shape: &[ShapeNode], delimiter: u8) {
    for (index, node) in shape.iter().enumerate() {
        if index > 0 {
            writer.byte(delimiter);
        }
        write_key(writer, &node.wire);
        if !node.children.is_empty() {
            writer.byte(b'{');
            write_field_group(writer, &node.children, delimiter);
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
                writer.byte(ctx.delimiter);
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
/// Exact-type pointer dispatch (optimization E1): one pointer compare per
/// common case instead of a chain of limited-API type-check calls. Exact
/// types cover ordinary data; subclasses take the original slow chain.
#[inline]
fn exact_type(obj: &Bound<'_, PyAny>) -> *mut pyo3::ffi::PyTypeObject {
    unsafe { pyo3::ffi::Py_TYPE(obj.as_ptr()) }
}

fn write_scalar_obj<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    obj: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let type_ptr = exact_type(obj);
    unsafe {
        use std::ptr::addr_of_mut;
        if type_ptr == addr_of_mut!(pyo3::ffi::PyUnicode_Type) {
            let text = obj.cast_unchecked::<PyString>().to_str()?;
            if needs_quote(text, ctx.delimiter) {
                write_quoted(writer, text);
            } else {
                writer.text(text);
            }
            return Ok(());
        }
        if type_ptr == addr_of_mut!(pyo3::ffi::PyLong_Type) {
            // Exact int: bool has its own type object, so no bool check needed.
            match obj.extract::<i64>() {
                Ok(small) => {
                    let mut buffer = itoa::Buffer::new();
                    writer.text(buffer.format(small));
                }
                Err(_) => writer.text(obj.str()?.to_str()?),
            }
            return Ok(());
        }
        if type_ptr == addr_of_mut!(pyo3::ffi::PyFloat_Type) {
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
        if type_ptr == addr_of_mut!(pyo3::ffi::PyBool_Type) {
            writer.bytes(if obj.is_truthy()? { b"true" } else { b"false" });
            return Ok(());
        }
    }
    if obj.is_none() {
        writer.bytes(b"null");
        return Ok(());
    }
    // Subclass slow path.
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
        if needs_quote(text, ctx.delimiter) {
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
    writer.text(&canonical_float(number));
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
        Val::Str(text) => Ok(quote_if_needed(text.to_str()?, ctx.delimiter)),
        _ => Err(encode_err(ctx, py, "not a scalar")),
    }
}

/// The canonical (JavaScript `Number.prototype.toString`) spelling: decimal
/// expansion while the decimal point lands within [-5, 21] digits of the
/// shortest representation, exponent form with an explicit sign outside it.
fn canonical_float(number: f64) -> String {
    if number == 0.0 {
        return "0".to_string();
    }
    let scientific = format!("{:e}", number.abs());
    let (mantissa, exponent_text) = scientific.split_once('e').expect("{:e} always has an e");
    let exponent: i32 = exponent_text.parse().expect("{:e} exponent is an integer");
    let digits: String = mantissa.chars().filter(|ch| *ch != '.').collect();
    let digits = digits.trim_end_matches('0');
    let digits = if digits.is_empty() { "0" } else { digits };
    let digit_count = digits.len() as i32;
    // The decimal point sits after `point` digits of `digits`.
    let point = exponent + 1;
    let sign = if number < 0.0 { "-" } else { "" };

    if digit_count <= point && point <= 21 {
        format!(
            "{sign}{digits}{}",
            "0".repeat((point - digit_count) as usize)
        )
    } else if 0 < point && point <= 21 {
        format!(
            "{sign}{}.{}",
            &digits[..point as usize],
            &digits[point as usize..]
        )
    } else if -6 < point && point <= 0 {
        format!("{sign}0.{}{digits}", "0".repeat((-point) as usize))
    } else {
        let mantissa = if digit_count == 1 {
            digits.to_string()
        } else {
            format!("{}.{}", &digits[..1], &digits[1..])
        };
        let exponent = point - 1;
        let exponent_sign = if exponent >= 0 { "+" } else { "-" };
        format!("{sign}{mantissa}e{exponent_sign}{}", exponent.abs())
    }
}

/// A string that could be mistaken for a number token (leading sign or
/// digit, only number-ish bytes, at least one digit) must be quoted even
/// when it is not itself a valid number — `05`, `+1`, `1.2.3`.
fn is_numeric_like(bytes: &[u8]) -> bool {
    let rest = match bytes.first() {
        Some(b'+' | b'-') => &bytes[1..],
        _ => bytes,
    };
    !rest.is_empty()
        && rest.iter().any(u8::is_ascii_digit)
        && rest
            .iter()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'.' | b'e' | b'E' | b'+' | b'-'))
}

fn needs_quote(text: &str, delimiter: u8) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return true;
    }
    if !matches!(classify_bare(bytes), ScalarToken::BareString(_)) {
        return true;
    }
    if is_numeric_like(bytes) {
        return true;
    }
    if bytes[0] == b' '
        || bytes[bytes.len() - 1] == b' '
        || matches!(bytes[0], b'"' | b'[' | b'{' | b'#' | b'\'')
    {
        return true;
    }
    if text == "-" || text.starts_with("- ") || text == "[]" {
        return true;
    }
    bytes.iter().any(|&byte| {
        byte == delimiter
            || matches!(byte, b':' | b'\n' | b'\r' | b'\t' | b'"' | b'\\')
            || byte < 0x20
    })
}

fn quote_if_needed(text: &str, delimiter: u8) -> String {
    if needs_quote(text, delimiter) {
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
        assert_eq!(canonical_float(123.456), "123.456");
        assert_eq!(canonical_float(-0.5), "-0.5");
        assert_eq!(canonical_float(1e-6), "0.000001");
        assert_eq!(canonical_float(1e-7), "1e-7");
        assert_eq!(canonical_float(2.5e-8), "2.5e-8");
        assert_eq!(canonical_float(1e20), "100000000000000000000");
        assert_eq!(canonical_float(1e21), "1e+21");
    }
}
