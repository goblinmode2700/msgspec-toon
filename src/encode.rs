//! The canonical encoder (canvas AD-004, §11).
//!
//! Walks Python values directly. `msgspec.Struct` instances are read through
//! a cached per-class encode plan and attribute access — never
//! `msgspec.to_builtins`. Arrays of same-shaped objects emit tabular form
//! with nested field groups; anything else falls back exactly as the
//! specification directs.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use pyo3::exceptions::{PyAttributeError, PyBufferError};
use pyo3::prelude::*;
use pyo3::sync::critical_section::with_critical_section;
use pyo3::types::{
    PyBool, PyByteArray, PyByteArrayMethods, PyBytes, PyBytesMethods, PyDict, PyFloat, PyFrozenSet,
    PyInt, PyList, PySet, PyString, PyTuple,
};

use crate::limits::{MAX_NESTING_DEPTH, reserve_bytes};
use crate::msgspec_capi::MsgspecCapi;
use crate::writer::Writer;

/// Capacity heuristic only — never policy: an assumed average encoded cell
/// width used to pre-reserve the output buffer for tabular rows.
const CELL_WIDTH_ESTIMATE: usize = 10;

const MAX_HOOK_DEPTH: usize = 8;
const NON_STRING_KEY_ERROR: &str =
    "object keys must be strings; convert with msgspec.to_builtins(..., str_keys=True)";

pub struct EncodeContext {
    pub enc_hook: Option<Py<PyAny>>,
    pub struct_base: Py<PyAny>,
    pub plan_source: Py<PyAny>,
    pub encode_error: Py<PyAny>,
    pub struct_api: Option<MsgspecCapi>,
    pub cache: Mutex<HashMap<usize, Arc<EncodePlan>>>,
    /// Spec-defined wire options (TOON 4.1 delimiter and indentation width);
    /// defaults produce canonical output.
    pub delimiter: u8,
    pub indent: usize,
}

const RAW_SCALAR_TYPE_ATTR: &str = "__toon_raw_scalar_type__";
const NATIVE_SCALAR_CHECK_ATTR: &str = "__toon_is_native_scalar__";
const DEFAULT_ENCODE_HOOK_ATTR: &str = "__toon_default_encode_hook__";

pub struct EncodePlan {
    /// Pins the class so the pointer cache key cannot be reused.
    #[allow(dead_code)]
    class: Py<PyAny>,
    fields: Vec<EncodeField>,
    array_like: bool,
    tag: Option<EncodeTag>,
    /// Precomputed tabular shape when the class's type plan proves every
    /// field is a primitive leaf or a (recursively static) nested Struct —
    /// rows of such a class need no runtime column scan at all.
    static_shape: Option<Arc<Vec<ShapeNode>>>,
}

struct EncodeTag {
    wire: String,
    value: Py<PyAny>,
}

struct EncodeField {
    access: StructAccess,
    wire: String,
}

enum StructAccess {
    Attr(Py<PyString>),
    Offset {
        attr: Py<PyString>,
        class: Py<PyAny>,
        offset: usize,
    },
}

enum Val<'py> {
    None,
    Bool(bool),
    /// Ordinary Python integers, plus private preformatted scalar text from
    /// the cold native-scalar hook. Both use the existing exact-text fallback
    /// when `i64` extraction is not applicable.
    IntegerOrRaw(Bound<'py, PyAny>),
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
    let graph = ctx.plan_source.bind(py).call1((class,))?;
    let root = graph.getattr("root")?.extract::<usize>()?;
    let mut visiting = vec![key];
    let plan = plan_from_spec(ctx, py, class, &graph, root, &mut visiting)?;
    ctx.cache.lock().unwrap().insert(key, plan.clone());
    Ok(plan)
}

/// Is a field's declared type always a tabular leaf (a primitive or an
/// optional/union of primitives)?
fn graph_node<'py>(graph: &Bound<'py, PyAny>, index: usize) -> PyResult<Bound<'py, PyAny>> {
    graph.getattr("nodes")?.get_item(index)
}

fn spec_is_leaf(graph: &Bound<'_, PyAny>, spec: &Bound<'_, PyAny>) -> PyResult<bool> {
    let kind = spec.getattr("kind")?.extract::<String>()?;
    match kind.as_str() {
        "none" | "bool" | "int" | "float" | "str" => Ok(true),
        "union" => {
            for member in spec.getattr("items")?.try_iter()? {
                let member = graph_node(graph, member?.extract::<usize>()?)?;
                if !spec_is_leaf(graph, &member)? {
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
    graph: &Bound<'_, PyAny>,
    node_index: usize,
    visiting: &mut Vec<usize>,
) -> PyResult<Arc<EncodePlan>> {
    let spec = graph_node(graph, node_index)?;
    let mut fields = Vec::new();
    let array_like = spec.getattr("array_like")?.extract::<bool>()?;
    let tag_field = spec.getattr("tag_field")?.extract::<Option<String>>()?;
    let tag_value = spec.getattr("tag_value")?;
    let tag = match (tag_field, tag_value.is_none()) {
        (Some(wire), false) => Some(EncodeTag {
            wire,
            value: tag_value.unbind(),
        }),
        _ => None,
    };
    let mut shape: Option<Vec<ShapeNode>> = (!array_like).then(Vec::new);
    if let (Some(nodes), Some(tag)) = (shape.as_mut(), tag.as_ref()) {
        nodes.push(ShapeNode {
            wire: tag.wire.clone(),
            access: Access::Constant(tag.value.clone_ref(py)),
            children: Vec::new(),
        });
    }
    let offsets = ctx
        .struct_api
        .as_ref()
        .map(|api| api.struct_offsets(py, class))
        .transpose()?;
    for (index, field) in spec.getattr("fields")?.try_iter()?.enumerate() {
        let field = field?;
        let name_text = field.getattr("python_name")?.extract::<String>()?;
        let attr = PyString::intern(py, &name_text).unbind();
        let access = match offsets.as_ref() {
            Some(offsets) => {
                let offset = offsets.get(index).copied().ok_or_else(|| {
                    pyo3::exceptions::PySystemError::new_err(
                        "msgspec C API field count is shorter than the encode plan",
                    )
                })?;
                StructAccess::Offset {
                    attr,
                    class: class.clone().unbind(),
                    offset,
                }
            }
            None => StructAccess::Attr(attr),
        };
        let wire = field.getattr("wire_name")?.extract::<String>()?;
        let value_index = field.getattr("plan")?.extract::<usize>()?;
        let value_spec = graph_node(graph, value_index)?;

        if let Some(nodes) = shape.as_mut() {
            let kind = value_spec.getattr("kind")?.extract::<String>()?;
            if kind == "struct" {
                let nested_class = value_spec.getattr("python_type")?;
                let nested_key = nested_class.as_ptr() as usize;
                if visiting.contains(&nested_key) {
                    shape = None;
                } else {
                    visiting.push(nested_key);
                    let nested =
                        plan_for_nested(ctx, py, &nested_class, graph, value_index, visiting)?;
                    visiting.pop();
                    match &nested.static_shape {
                        Some(children) => nodes.push(ShapeNode {
                            wire: wire.clone(),
                            access: access.clone_ref(py).into(),
                            children: clone_nodes(py, children),
                        }),
                        None => shape = None,
                    }
                }
            } else if spec_is_leaf(graph, &value_spec)? {
                nodes.push(ShapeNode {
                    wire: wire.clone(),
                    access: access.clone_ref(py).into(),
                    children: Vec::new(),
                });
            } else {
                shape = None;
            }
        }

        fields.push(EncodeField { access, wire });
    }
    if offsets
        .as_ref()
        .is_some_and(|offsets| offsets.len() != fields.len())
    {
        return Err(pyo3::exceptions::PySystemError::new_err(
            "msgspec C API field count differs from the encode plan",
        ));
    }
    let static_shape = match shape {
        Some(nodes) if !nodes.is_empty() => Some(Arc::new(nodes)),
        _ => None,
    };
    Ok(Arc::new(EncodePlan {
        class: class.clone().unbind(),
        fields,
        array_like,
        tag,
        static_shape,
    }))
}

fn plan_for_nested(
    ctx: &EncodeContext,
    py: Python<'_>,
    class: &Bound<'_, PyAny>,
    graph: &Bound<'_, PyAny>,
    node_index: usize,
    visiting: &mut Vec<usize>,
) -> PyResult<Arc<EncodePlan>> {
    let key = class.as_ptr() as usize;
    if let Some(plan) = ctx.cache.lock().unwrap().get(&key) {
        return Ok(plan.clone());
    }
    let plan = plan_from_spec(ctx, py, class, graph, node_index, visiting)?;
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
                Access::Offset {
                    attr,
                    class,
                    offset,
                } => Access::Offset {
                    attr: attr.clone_ref(py),
                    class: class.clone_ref(py),
                    offset: *offset,
                },
                Access::Item(key) => Access::Item(key.clone_ref(py)),
                Access::Constant(value) => Access::Constant(value.clone_ref(py)),
            },
            children: clone_nodes(py, &node.children),
        })
        .collect()
}

#[cold]
#[inline(never)]
fn classify_fallback<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    hook_depth: usize,
) -> PyResult<Val<'py>> {
    if exact_type(obj) == std::ptr::addr_of_mut!(pyo3::ffi::PyBytes_Type) {
        let encoded = checked_base64(ctx, py, obj.cast::<PyBytes>()?.as_bytes())?;
        let text = std::str::from_utf8(&encoded).expect("base64 output is ASCII");
        return Ok(Val::Str(PyString::new(py, text)));
    }
    if let Some(bytes) = exact_buffer_bytes(obj)? {
        let encoded = checked_base64(ctx, py, &bytes)?;
        let text = std::str::from_utf8(&encoded).expect("base64 output is ASCII");
        return Ok(Val::Str(PyString::new(py, text)));
    }
    if obj.is_instance_of::<PySet>() || obj.is_instance_of::<PyFrozenSet>() {
        // Match msgspec's default encoder: a set is an array in its current
        // interpreter iteration order. Collect owned references, not a Python
        // list projection. `try_iter` also turns concurrent mutation into a
        // Python exception instead of the panic used by PyO3's set iterator.
        let items = obj.try_iter()?.collect::<PyResult<Vec<_>>>()?;
        return Ok(Val::Seq(items));
    }
    if let Some(hook) = ctx.enc_hook.as_ref() {
        if hook_depth >= MAX_HOOK_DEPTH {
            return Err(encode_err(ctx, py, "enc_hook recursion limit exceeded"));
        }
        let replaced = hook.bind(py).call1((obj,))?;
        if let Some(raw) = raw_scalar(ctx, py, &replaced)? {
            return Ok(Val::IntegerOrRaw(raw.into_any()));
        }
        return classify(ctx, py, &replaced, hook_depth + 1);
    }
    let replaced = default_encode_hook(ctx, py, obj)?;
    if let Some(raw) = raw_scalar(ctx, py, &replaced)? {
        return Ok(Val::IntegerOrRaw(raw.into_any()));
    }
    classify(ctx, py, &replaced, hook_depth + 1)
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
        return Ok(Val::IntegerOrRaw(obj.clone()));
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
    // Keep native projections and hook dispatch out of the common container
    // classifier. This fallback is reached only after every native hot type
    // has returned.
    classify_fallback(ctx, py, obj, hook_depth)
}

/// A pending entry key: a wire name borrowed from the plan inside the `Val`,
/// or the dict key object itself, read at write time. Carrying a borrow or
/// the object instead of a copied `String` is optimization R2-C: the copy was
/// one allocation per entry, per call, on every non-tabular object.
enum EntryText<'value, 'py> {
    Wire(&'value str),
    Object(Bound<'py, PyString>),
}

impl EntryText<'_, '_> {
    fn as_str(&self) -> PyResult<&str> {
        match self {
            EntryText::Wire(text) => Ok(text),
            EntryText::Object(text) => text.to_str(),
        }
    }
}

fn object_pairs<'value, 'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    value: &'value Val<'py>,
) -> PyResult<Vec<(EntryText<'value, 'py>, Bound<'py, PyAny>)>> {
    match value {
        Val::Dict(map) => {
            let mut pairs = Vec::with_capacity(map.len());
            for (key, item) in map.iter() {
                let Ok(key_text) = key.cast_into::<PyString>() else {
                    return Err(encode_err(ctx, py, NON_STRING_KEY_ERROR));
                };
                pairs.push((EntryText::Object(key_text), item));
            }
            Ok(pairs)
        }
        Val::Struct(instance, plan) => {
            if plan.array_like {
                return Err(encode_err(ctx, py, "array-like Struct is not an object"));
            }
            let mut pairs = Vec::with_capacity(plan.fields.len() + usize::from(plan.tag.is_some()));
            if let Some(tag) = &plan.tag {
                pairs.push((
                    EntryText::Wire(tag.wire.as_str()),
                    tag.value.bind(py).clone(),
                ));
            }
            for field in &plan.fields {
                let item = struct_field(py, instance, &field.access)?;
                pairs.push((EntryText::Wire(field.wire.as_str()), item));
            }
            Ok(pairs)
        }
        _ => Err(encode_err(ctx, py, "not an object")),
    }
}

fn struct_sequence<'py>(
    py: Python<'py>,
    instance: &Bound<'py, PyAny>,
    plan: &EncodePlan,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut items = Vec::with_capacity(plan.fields.len() + usize::from(plan.tag.is_some()));
    if let Some(tag) = &plan.tag {
        items.push(tag.value.bind(py).clone());
    }
    for field in &plan.fields {
        items.push(struct_field(py, instance, &field.access)?);
    }
    Ok(items)
}

pub fn encode_root(
    ctx: &EncodeContext,
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Vec<u8>> {
    let mut writer = Writer::with_capacity(256, ctx.indent);
    let value = classify(ctx, py, obj, 0)?;
    match &value {
        Val::Struct(instance, plan) if plan.array_like => {
            let items = struct_sequence(py, instance, plan)?;
            write_array(ctx, py, &mut writer, None, &items, 0, 0, false)?;
        }
        Val::Dict(_) | Val::Struct(_, _) => match root_object_decision(ctx, py, &value, 0)? {
            ObjectRenderDecision::Keyed(keyed) => {
                write_keyed(ctx, py, &mut writer, None, &keyed, 0, false)?;
            }
            ObjectRenderDecision::Entries(pairs) => {
                write_entries(ctx, py, &mut writer, &pairs, 0)?;
            }
        },
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
    pairs: &[(EntryText<'_, 'py>, Bound<'py, PyAny>)],
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_NESTING_DEPTH {
        return Err(encode_err(ctx, py, "nesting depth limit exceeded"));
    }
    for (key, item) in pairs {
        write_entry(ctx, py, writer, key.as_str()?, item, depth, false)?;
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
        Val::Struct(instance, plan) if plan.array_like => {
            let items = struct_sequence(py, instance, plan)?;
            write_array(ctx, py, writer, Some(key), &items, depth, 0, inline)
        }
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
            write_entry_scalar(ctx, py, writer, &value)?;
            writer.newline();
            Ok(())
        }
    }
}

#[inline(never)]
fn write_entry_scalar<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    value: &Val<'py>,
) -> PyResult<()> {
    if let Val::Str(text) = value {
        let text = text.to_str()?;
        let bytes = text.as_bytes();
        if bytes.len() >= 96 && !matches!(bytes[0], b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-')
        {
            let quote = memchr::memchr3(ctx.delimiter, b':', b'"', bytes).is_some()
                || memchr::memchr(b'\\', bytes).is_some()
                || bytes.iter().any(|&byte| byte < 0x20);
            if quote {
                write_quoted(writer, text);
            } else {
                writer.text(text);
            }
            return Ok(());
        }
    }
    write_scalar(ctx, py, writer, value)
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

    let tabular_eligible = key.is_some() || !inline;
    let mut discovered_shape = if tabular_eligible && !is_exact_scalar_obj(&items[0]) {
        build_shape(ctx, py, items, nesting)?
    } else {
        None
    };

    let mut all_scalars = discovered_shape.is_none();
    if all_scalars {
        for item in items {
            if !is_scalar_obj(ctx, py, item)? {
                all_scalars = false;
                break;
            }
        }
    }
    if all_scalars {
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
    if tabular_eligible && discovered_shape.is_none() {
        discovered_shape = build_shape(ctx, py, items, nesting)?;
    }
    if let Some(shape) = discovered_shape {
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
        Val::Struct(instance, plan) if plan.array_like => {
            let items = struct_sequence(py, instance, plan)?;
            writer.indent(depth);
            writer.bytes(b"- ");
            write_array(ctx, py, writer, None, &items, depth, nesting + 1, true)
        }
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
            write_entry(
                ctx,
                py,
                writer,
                first_key.as_str()?,
                first_item,
                depth + 1,
                true,
            )?;
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
    entries: Vec<(Bound<'py, PyString>, Bound<'py, PyAny>)>,
    shape: Shape,
}

/// One root-object decision. The fallback entry view survives a failed keyed
/// classification, so validation and rendering consume the same dictionary
/// walk instead of rebuilding it through `object_pairs`.
enum ObjectRenderDecision<'value, 'py> {
    Entries(Vec<(EntryText<'value, 'py>, Bound<'py, PyAny>)>),
    Keyed(KeyedShape<'py>),
}

fn root_object_decision<'value, 'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    value: &'value Val<'py>,
    depth: usize,
) -> PyResult<ObjectRenderDecision<'value, 'py>> {
    let Val::Dict(map) = value else {
        return Ok(ObjectRenderDecision::Entries(object_pairs(ctx, py, value)?));
    };

    let mut entries = Vec::with_capacity(map.len());
    let mut rows = (map.len() >= 2).then(|| Vec::with_capacity(map.len()));
    for (key, item) in map.iter() {
        let Ok(key_text) = key.cast_into::<PyString>() else {
            return Err(encode_err(ctx, py, NON_STRING_KEY_ERROR));
        };
        if let Some(candidate_rows) = rows.as_mut() {
            if item.is_instance_of::<PyDict>() || item.is_instance(ctx.struct_base.bind(py))? {
                candidate_rows.push(item.clone());
            } else {
                rows = None;
            }
        }
        entries.push((key_text, item));
    }

    if let Some(rows) = rows
        && let Some(shape) = build_shape(ctx, py, &rows, depth)?
    {
        return Ok(ObjectRenderDecision::Keyed(KeyedShape { entries, shape }));
    }

    Ok(ObjectRenderDecision::Entries(
        entries
            .into_iter()
            .map(|(key, item)| (EntryText::Object(key), item))
            .collect(),
    ))
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
    // Most probed objects are plain configs whose first value is a scalar.
    // Settling that case before the two vectors below exist keeps the probe
    // allocation-free on the common miss (optimization R2-D).
    if let Some((_, first_item)) = map.iter().next()
        && !(first_item.is_instance_of::<PyDict>()
            || first_item.is_instance(ctx.struct_base.bind(py))?)
    {
        return Ok(None);
    }
    let mut entries = Vec::with_capacity(map.len());
    let mut rows = Vec::with_capacity(map.len());
    for (key, item) in map.iter() {
        let Ok(key_text) = key.cast_into::<PyString>() else {
            return Ok(None);
        };
        if !(item.is_instance_of::<PyDict>() || item.is_instance(ctx.struct_base.bind(py))?) {
            return Ok(None);
        }
        entries.push((key_text, item.clone()));
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
        write_key(writer, row_key.to_str()?);
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
    Offset {
        attr: Py<PyString>,
        class: Py<PyAny>,
        offset: usize,
    },
    Item(Py<PyAny>),
    Constant(Py<PyAny>),
}

impl StructAccess {
    fn clone_ref(&self, py: Python<'_>) -> Self {
        match self {
            Self::Attr(attr) => Self::Attr(attr.clone_ref(py)),
            Self::Offset {
                attr,
                class,
                offset,
            } => Self::Offset {
                attr: attr.clone_ref(py),
                class: class.clone_ref(py),
                offset: *offset,
            },
        }
    }
}

impl From<StructAccess> for Access {
    fn from(value: StructAccess) -> Self {
        match value {
            StructAccess::Attr(attr) => Self::Attr(attr),
            StructAccess::Offset {
                attr,
                class,
                offset,
            } => Self::Offset {
                attr,
                class,
                offset,
            },
        }
    }
}

#[inline(always)]
fn struct_field<'py>(
    py: Python<'py>,
    instance: &Bound<'py, PyAny>,
    access: &StructAccess,
) -> PyResult<Bound<'py, PyAny>> {
    match access {
        StructAccess::Attr(attr) => instance.getattr(attr.bind(py)),
        StructAccess::Offset { attr, offset, .. } => offset_field(py, instance, attr, *offset),
    }
}

#[inline(always)]
fn offset_field<'py>(
    py: Python<'py>,
    instance: &Bound<'py, PyAny>,
    attr: &Py<PyString>,
    offset: usize,
) -> PyResult<Bound<'py, PyAny>> {
    // SAFETY: the optional C API supplies offsets for this exact pinned Struct
    // class. Callers compare the runtime type before taking the offset path.
    // The object critical section protects slot access on free-threaded
    // CPython. `from_borrowed_ptr` acquires a strong reference before the
    // critical section ends; it does not steal the Struct-owned slot.
    with_critical_section(instance, || unsafe {
        let slot = (instance.as_ptr() as *const u8)
            .add(offset)
            .cast::<*mut pyo3::ffi::PyObject>();
        let value = *slot;
        if value.is_null() {
            let repr = attr.bind(py).repr()?;
            let name = repr.to_string_lossy();
            Err(PyAttributeError::new_err(format!(
                "Struct field {name} is unset"
            )))
        } else {
            Ok(Bound::from_borrowed_ptr(py, value))
        }
    })
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
fn is_scalar_obj(ctx: &EncodeContext, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<bool> {
    let type_ptr = exact_type(obj);
    {
        use std::ptr::addr_of_mut;
        if type_ptr == addr_of_mut!(pyo3::ffi::PyUnicode_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyLong_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyFloat_Type)
            || type_ptr == addr_of_mut!(pyo3::ffi::PyBool_Type)
        {
            return Ok(true);
        }
    }
    if obj.is_none() {
        return Ok(true);
    }
    if type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyDict_Type) {
        return Ok(false);
    }
    if obj.is_instance(ctx.struct_base.bind(py))? || obj.is_instance_of::<PyDict>() {
        return Ok(false);
    }
    if obj.is_instance_of::<PyBool>()
        || obj.is_instance_of::<PyInt>()
        || obj.is_instance_of::<PyFloat>()
        || obj.is_instance_of::<PyString>()
    {
        return Ok(true);
    }
    ctx.plan_source
        .bind(py)
        .getattr(NATIVE_SCALAR_CHECK_ATTR)?
        .call1((obj,))?
        .is_truthy()
}

#[inline]
fn is_exact_scalar_obj(obj: &Bound<'_, PyAny>) -> bool {
    let type_ptr = exact_type(obj);
    type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyUnicode_Type)
        || type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyLong_Type)
        || type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyFloat_Type)
        || type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyBool_Type)
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
        if plan.array_like {
            return Ok(None);
        }
        if let Some(static_nodes) = &plan.static_shape {
            return Ok(Some(Shape::Shared(static_nodes.clone())));
        }
        let mut accessors = Vec::with_capacity(plan.fields.len() + usize::from(plan.tag.is_some()));
        if let Some(tag) = &plan.tag {
            accessors.push((tag.wire.clone(), Access::Constant(tag.value.clone_ref(py))));
        }
        accessors.extend(
            plan.fields
                .iter()
                .map(|field| (field.wire.clone(), field.access.clone_ref(py).into())),
        );
        accessors
    } else if let Ok(first_map) = first.cast::<PyDict>() {
        let mut first_keys = Vec::with_capacity(first_map.len());
        for key in first_map.keys() {
            let Ok(text) = key.cast::<PyString>() else {
                return Ok(None);
            };
            first_keys.push((text.to_str()?.to_string(), key.clone().unbind()));
        }
        for row in rows.iter().skip(1) {
            let Ok(map) = row.cast::<PyDict>() else {
                return Ok(None);
            };
            if map.len() != first_keys.len() {
                return Ok(None);
            }
            // Same key set is enough; the column pass fetches by name and
            // bails if any key is absent. With equal lengths, hashed
            // membership for every first-row key also proves there is no
            // extra key. Per-row encounter order may differ (TOON 4.1 §9.3).
            for (_, key) in &first_keys {
                if !map.contains(key.bind(py))? {
                    return Ok(None);
                }
            }
        }
        first_keys
            .into_iter()
            .map(|(key, key_obj)| (key, Access::Item(key_obj)))
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
                Access::Offset { attr, offset, .. } => offset_field(py, row, attr, *offset)?,
                Access::Item(key) => match row.cast::<PyDict>() {
                    Ok(map) => match map.get_item(key.bind(py))? {
                        Some(item) => item,
                        None => return Ok(None),
                    },
                    Err(_) => return Ok(None),
                },
                Access::Constant(value) => value.bind(py).clone(),
            };
            column.push(item);
        }
        let mut all_scalars = true;
        for item in &column {
            if is_exact_scalar_obj(item) || item.is_none() {
                continue;
            }
            if !is_scalar_obj(ctx, py, item)? {
                all_scalars = false;
                break;
            }
        }
        if all_scalars {
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
    // A static nested shape comes from the declared field type, while callers
    // may still place a Struct subclass there. Validate once for this Struct
    // level; every offset in one level belongs to the same pinned class.
    let offsets_match = shape.first().is_none_or(|node| match &node.access {
        Access::Offset { class, .. } => std::ptr::eq(
            // SAFETY: `row` is a live `Bound` Python object. Reading its type
            // pointer does not dereference user-controlled payload memory.
            unsafe { pyo3::ffi::Py_TYPE(row.as_ptr()) },
            class.as_ptr().cast(),
        ),
        _ => true,
    });
    for node in shape {
        let item = match &node.access {
            Access::Attr(attr) => row.getattr(attr.bind(py))?,
            Access::Offset { attr, offset, .. } if offsets_match => {
                offset_field(py, row, attr, *offset)?
            }
            Access::Offset { attr, .. } => row.getattr(attr.bind(py))?,
            Access::Item(key) => match row.cast::<PyDict>() {
                Ok(map) => map
                    .get_item(key.bind(py))?
                    .ok_or_else(|| encode_err(ctx, py, "row lost a classified column"))?,
                Err(_) => return Err(encode_err(ctx, py, "row lost its classified shape")),
            },
            Access::Constant(value) => value.bind(py).clone(),
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
    // SAFETY: `obj` is a live `Bound` reference, so its CPython header and
    // exact type pointer remain valid for this call.
    unsafe { pyo3::ffi::Py_TYPE(obj.as_ptr()) }
}

/// Copy the two exact buffer-backed types that msgspec projects as binary
/// values. Exact-type dispatch intentionally keeps `bytes` and `bytearray`
/// subclasses on the hook/refusal path. msgspec accepts only C-contiguous
/// memoryviews, so check that boundary before copying through `tobytes`.
#[cold]
#[inline(never)]
fn exact_buffer_bytes(obj: &Bound<'_, PyAny>) -> PyResult<Option<Vec<u8>>> {
    let type_ptr = exact_type(obj);
    if type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyByteArray_Type) {
        return Ok(Some(obj.cast::<PyByteArray>()?.to_vec()));
    }
    if type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyMemoryView_Type) {
        if !obj.getattr("c_contiguous")?.extract::<bool>()? {
            return Err(PyBufferError::new_err(
                "memoryview: underlying buffer is not C-contiguous",
            ));
        }
        let copied = obj.call_method0("tobytes")?;
        return Ok(Some(copied.cast::<PyBytes>()?.as_bytes().to_vec()));
    }
    Ok(None)
}

#[cold]
#[inline(never)]
fn raw_scalar<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyString>>> {
    let marker = ctx.plan_source.bind(py).getattr(RAW_SCALAR_TYPE_ATTR)?;
    if obj.get_type().as_any().is(&marker) {
        return Ok(Some(obj.cast::<PyString>()?.clone()));
    }
    Ok(None)
}

#[cold]
#[inline(never)]
fn default_encode_hook<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    ctx.plan_source
        .bind(py)
        .getattr(DEFAULT_ENCODE_HOOK_ATTR)?
        .call1((obj,))
}

fn write_scalar_obj<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    obj: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let type_ptr = exact_type(obj);
    // SAFETY: each unchecked cast is guarded by exact pointer equality with
    // the corresponding immortal CPython type object. No subclass enters an
    // exact-type branch; subclasses use the checked slow path below.
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
    write_scalar_fallback(ctx, py, writer, obj)
}

#[cold]
#[inline(never)]
fn write_scalar_fallback<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    obj: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let type_ptr = exact_type(obj);
    if type_ptr == std::ptr::addr_of_mut!(pyo3::ffi::PyBytes_Type) {
        return write_bytes_scalar(ctx, py, writer, obj.cast::<PyBytes>()?);
    }
    if let Some(bytes) = exact_buffer_bytes(obj)? {
        return write_binary_scalar(ctx, py, writer, &bytes);
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
    let replaced = match ctx.enc_hook.as_ref() {
        Some(hook) => hook.bind(py).call1((obj,))?,
        None => default_encode_hook(ctx, py, obj)?,
    };
    if let Some(raw) = raw_scalar(ctx, py, &replaced)? {
        writer.text(raw.to_str()?);
        return Ok(());
    }
    write_scalar_obj(ctx, py, writer, &replaced)
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

const BASE64_ALPHABET: &[u8; 64] =
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// Encode with msgspec's standard padded base64 value projection. This ports
/// the pinned msgspec 0.21.1 algorithm locally, without a runtime dependency.
#[cold]
#[inline(never)]
fn base64_encode(input: &[u8]) -> Vec<u8> {
    let encoded_len = input.len().div_ceil(3) * 4;
    let mut output = Vec::with_capacity(encoded_len);
    let mut chunks = input.chunks_exact(3);
    for chunk in &mut chunks {
        let bits = (u32::from(chunk[0]) << 16) | (u32::from(chunk[1]) << 8) | u32::from(chunk[2]);
        output.push(BASE64_ALPHABET[((bits >> 18) & 0x3f) as usize]);
        output.push(BASE64_ALPHABET[((bits >> 12) & 0x3f) as usize]);
        output.push(BASE64_ALPHABET[((bits >> 6) & 0x3f) as usize]);
        output.push(BASE64_ALPHABET[(bits & 0x3f) as usize]);
    }
    match chunks.remainder() {
        [first] => {
            let bits = u32::from(*first) << 16;
            output.push(BASE64_ALPHABET[((bits >> 18) & 0x3f) as usize]);
            output.push(BASE64_ALPHABET[((bits >> 12) & 0x3f) as usize]);
            output.extend_from_slice(b"==");
        }
        [first, second] => {
            let bits = (u32::from(*first) << 16) | (u32::from(*second) << 8);
            output.push(BASE64_ALPHABET[((bits >> 18) & 0x3f) as usize]);
            output.push(BASE64_ALPHABET[((bits >> 12) & 0x3f) as usize]);
            output.push(BASE64_ALPHABET[((bits >> 6) & 0x3f) as usize]);
            output.push(b'=');
        }
        [] => {}
        _ => unreachable!("chunks_exact(3) leaves at most two bytes"),
    }
    debug_assert_eq!(output.len(), encoded_len);
    output
}

#[cold]
#[inline(never)]
fn checked_base64(ctx: &EncodeContext, py: Python<'_>, input: &[u8]) -> PyResult<Vec<u8>> {
    if input.len() > u32::MAX as usize {
        return Err(encode_err(
            ctx,
            py,
            "bytes objects longer than 2**32 - 1 are not encodable",
        ));
    }
    Ok(base64_encode(input))
}

#[cold]
#[inline(never)]
fn write_bytes_scalar(
    ctx: &EncodeContext,
    py: Python<'_>,
    writer: &mut Writer,
    value: &Bound<'_, PyBytes>,
) -> PyResult<()> {
    write_binary_scalar(ctx, py, writer, value.as_bytes())
}

#[cold]
#[inline(never)]
fn write_binary_scalar(
    ctx: &EncodeContext,
    py: Python<'_>,
    writer: &mut Writer,
    value: &[u8],
) -> PyResult<()> {
    let encoded = checked_base64(ctx, py, value)?;
    let text = std::str::from_utf8(&encoded).expect("base64 output is ASCII");
    if needs_quote(text, ctx.delimiter) {
        write_quoted(writer, text);
    } else {
        writer.bytes(&encoded);
    }
    Ok(())
}

const HEX_DIGITS: &[u8; 16] = b"0123456789abcdef";

/// The one escape implementation (optimization E5): clean spans are copied in
/// bulk instead of re-encoded character by character, and only the bytes that
/// need an escape interrupt the copy. Multi-byte UTF-8 sequences are all
/// >= 0x80, so they pass through inside the clean spans untouched.
fn write_quoted(writer: &mut Writer, text: &str) {
    writer.byte(b'"');
    let bytes = text.as_bytes();
    let mut clean_start = 0;
    for (position, &byte) in bytes.iter().enumerate() {
        let escape: &[u8] = match byte {
            b'"' => b"\\\"",
            b'\\' => b"\\\\",
            b'\n' => b"\\n",
            b'\r' => b"\\r",
            b'\t' => b"\\t",
            control if control < 0x20 => {
                writer.bytes(&bytes[clean_start..position]);
                writer.bytes(b"\\u00");
                writer.byte(HEX_DIGITS[usize::from(control >> 4)]);
                writer.byte(HEX_DIGITS[usize::from(control & 0x0F)]);
                clean_start = position + 1;
                continue;
            }
            _ => continue,
        };
        writer.bytes(&bytes[clean_start..position]);
        writer.bytes(escape);
        clean_start = position + 1;
    }
    writer.bytes(&bytes[clean_start..]);
    writer.byte(b'"');
}

/// Write a classified scalar straight into the output buffer (optimization
/// R2-B). The previous shape built a `String` per scalar — one allocation for
/// every `key: value` entry — and copied it into the writer; the row path
/// never paid this, which is why entries cost ~3x a tabular cell. The number
/// spellings are the row path's own (`itoa`, `write_float`), so the two paths
/// cannot drift apart.
fn write_scalar<'py>(
    ctx: &EncodeContext,
    py: Python<'py>,
    writer: &mut Writer,
    value: &Val<'py>,
) -> PyResult<()> {
    match value {
        Val::None => writer.bytes(b"null"),
        Val::Bool(true) => writer.bytes(b"true"),
        Val::Bool(false) => writer.bytes(b"false"),
        Val::IntegerOrRaw(obj) => match obj.extract::<i64>() {
            Ok(small) => {
                let mut buffer = itoa::Buffer::new();
                writer.text(buffer.format(small));
            }
            Err(_) => writer.text(obj.str()?.to_str()?),
        },
        Val::Float(number) => write_float(writer, *number),
        Val::Str(text) => {
            let text = text.to_str()?;
            if needs_quote(text, ctx.delimiter) {
                write_quoted(writer, text);
            } else {
                writer.text(text);
            }
        }
        _ => return Err(encode_err(ctx, py, "not a scalar")),
    }
    Ok(())
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

/// One scan (optimization E5) deciding whether a string must be quoted. The
/// literal keywords come first; the loop then answers both remaining
/// questions at once: does any byte force quoting, and could the whole token
/// be mistaken for a number — leading sign or digit, only number-ish bytes,
/// at least one digit (`05`, `+1`, `1.2.3`)? Every valid number token is
/// also numeric-like, so the number grammar needs no separate pass here.
fn needs_quote(text: &str, delimiter: u8) -> bool {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return true;
    }
    if matches!(bytes, b"null" | b"true" | b"false" | b"-" | b"[]") {
        return true;
    }
    if bytes[0] == b' '
        || bytes[bytes.len() - 1] == b' '
        || matches!(bytes[0], b'"' | b'[' | b'{' | b'#' | b'\'')
        || bytes.starts_with(b"- ")
    {
        return true;
    }
    let forces_quote =
        |byte: u8| byte == delimiter || matches!(byte, b':' | b'"' | b'\\') || byte < 0x20;
    // Ported from the first-byte split in serde_toon_format's string
    // analyzer (E8). Most payload strings begin with an ordinary letter; a
    // byte outside the numeric-like alphabet proves the whole token cannot be
    // mistaken for a number, so that common path only scans for wire syntax.
    if !matches!(bytes[0], b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-') {
        return bytes.iter().copied().any(forces_quote);
    }
    let sign_prefixed = matches!(bytes[0], b'+' | b'-');
    let mut any_digit = false;
    let mut all_numeric_ish = true;
    for (position, &byte) in bytes.iter().enumerate() {
        // `\n`, `\r`, and `\t` are all below 0x20.
        if forces_quote(byte) {
            return true;
        }
        if position == 0 && sign_prefixed {
            continue;
        }
        if byte.is_ascii_digit() {
            any_digit = true;
        } else if !matches!(byte, b'.' | b'e' | b'E' | b'+' | b'-') {
            all_numeric_ish = false;
        }
    }
    any_digit && all_numeric_ish
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
        write_quoted(writer, key);
    } else {
        writer.text(key);
    }
}

#[cfg(test)]
mod tests {
    use super::{base64_encode, canonical_float};

    #[test]
    fn bytes_use_standard_padded_base64() {
        for (plain, encoded) in [
            (b"".as_slice(), b"".as_slice()),
            (b"f".as_slice(), b"Zg==".as_slice()),
            (b"fo".as_slice(), b"Zm8=".as_slice()),
            (b"foo".as_slice(), b"Zm9v".as_slice()),
            (b"foob".as_slice(), b"Zm9vYg==".as_slice()),
            (b"fooba".as_slice(), b"Zm9vYmE=".as_slice()),
            (b"foobar".as_slice(), b"Zm9vYmFy".as_slice()),
        ] {
            assert_eq!(base64_encode(plain), encoded);
        }
    }

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

#[cfg(test)]
mod e5_differential {
    use super::*;

    #[test]
    fn classified_value_stays_compact() {
        assert_eq!(std::mem::size_of::<Val<'_>>(), 24);
    }

    /// The implementations E5 replaced, kept as the differential oracle: a
    /// classify pass, an independent numeric-like pass, then a forbidden-byte
    /// pass; and escaping that re-encoded every character through UTF-8.
    fn needs_quote_multi_pass(text: &str, delimiter: u8) -> bool {
        fn is_numeric_like(bytes: &[u8]) -> bool {
            let rest = match bytes.first() {
                Some(b'+' | b'-') => &bytes[1..],
                _ => bytes,
            };
            !rest.is_empty()
                && rest.iter().any(u8::is_ascii_digit)
                && rest.iter().all(|byte| {
                    byte.is_ascii_digit() || matches!(byte, b'.' | b'e' | b'E' | b'+' | b'-')
                })
        }
        let bytes = text.as_bytes();
        if bytes.is_empty() {
            return true;
        }
        if !matches!(
            crate::scalar::classify_bare(bytes),
            crate::event::ScalarToken::BareString(_)
        ) {
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

    fn quote_char_wise(text: &str) -> String {
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

    fn quote_span_wise(text: &str) -> String {
        let mut writer = Writer::with_capacity(text.len() + 2, 2);
        write_quoted(&mut writer, text);
        String::from_utf8(writer.finish()).expect("escaped output is valid UTF-8")
    }

    /// Every string the encoder can be handed is either quoted or not, and if
    /// quoted, escaped. Both decisions are checked against the replaced
    /// implementations over an alphabet chosen to hit every branch: the
    /// delimiters, the structural bytes, control bytes, the number grammar,
    /// and multi-byte UTF-8.
    #[test]
    fn one_pass_quoting_matches_the_multi_pass_one() {
        const ALPHABET: &[&str] = &[
            "", "a", "0", "1", "9", ".", "e", "E", "+", "-", " ", ":", ",", "\t", "|", "\"", "\\",
            "\n", "\r", "[", "]", "{", "#", "'", "\u{0}", "\u{1f}", "\u{7f}", "é", "→", "𝄞", "n",
            "u", "l",
        ];
        const DELIMITERS: [u8; 3] = *b",\t|";
        let mut checked = 0usize;
        for first in ALPHABET {
            for second in ALPHABET {
                for third in ALPHABET {
                    let text = format!("{first}{second}{third}");
                    for delimiter in DELIMITERS {
                        assert_eq!(
                            needs_quote(&text, delimiter),
                            needs_quote_multi_pass(&text, delimiter),
                            "needs_quote diverged on {text:?} delimiter {delimiter:?}"
                        );
                        checked += 1;
                    }
                    assert_eq!(
                        quote_span_wise(&text),
                        quote_char_wise(&text),
                        "escaping diverged on {text:?}"
                    );
                }
            }
        }
        for literal in [
            "null", "true", "false", "[]", "- x", "-", "05", "+1", "1.2.3", "1e5",
        ] {
            for delimiter in DELIMITERS {
                assert_eq!(
                    needs_quote(literal, delimiter),
                    needs_quote_multi_pass(literal, delimiter),
                    "needs_quote diverged on {literal:?}"
                );
                checked += 1;
            }
            assert_eq!(quote_span_wise(literal), quote_char_wise(literal));
        }
        assert!(checked > 100_000, "differential was too small: {checked}");
        println!("E5 differential: {checked} (string, delimiter) pairs, zero divergences");
    }
}
