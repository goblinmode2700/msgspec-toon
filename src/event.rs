//! Structural events and the consumer contract (canvas AD-002).
//!
//! The parser never knows about Python or msgspec. It emits borrowed events
//! into a `Consumer`; the untyped, typed, and validation consumers share it.

use crate::error::{Fault, Position};

#[derive(Debug, Clone, Copy)]
pub enum StringToken<'a> {
    /// A bare (unquoted) key or string; bytes are exactly the source slice.
    Bare(&'a [u8]),
    /// The inner bytes of a quoted string. `escaped` says whether any escape
    /// sequences occur (already validated by the parser).
    Quoted { inner: &'a [u8], escaped: bool },
}

#[derive(Debug, Clone, Copy)]
pub enum ScalarToken<'a> {
    Null,
    Bool(bool),
    Integer(&'a [u8]),
    Float(&'a [u8]),
    BareString(&'a [u8]),
    Quoted { inner: &'a [u8], escaped: bool },
}

/// One field in a tabular header. A node with children is a nested field
/// group; a node without children consumes one row cell.
#[derive(Debug, Clone)]
pub struct FieldNode<'a> {
    pub name: StringToken<'a>,
    pub children: Vec<FieldNode<'a>>,
}

impl FieldNode<'_> {
    pub fn leaf_count(&self) -> usize {
        if self.children.is_empty() {
            1
        } else {
            self.children.iter().map(FieldNode::leaf_count).sum()
        }
    }
}

/// Borrowed lookahead for one nested field group in one tabular row.
///
/// The probe owns no source bytes and builds no value tree. Consumers can
/// inspect the immediate scalar fields to select a schema plan before the
/// matching object frame opens. The parser still consumes the same cells
/// through the normal event path after selection.
#[derive(Debug, Clone, Copy)]
pub struct ObjectProbe<'fields, 'input> {
    fields: &'fields [FieldNode<'input>],
    cells: &'fields [&'input [u8]],
}

impl<'fields, 'input> ObjectProbe<'fields, 'input> {
    pub fn new(fields: &'fields [FieldNode<'input>], cells: &'fields [&'input [u8]]) -> Self {
        Self { fields, cells }
    }

    pub fn scalar_cells(self) -> ObjectScalarCells<'fields, 'input> {
        ObjectScalarCells {
            fields: self.fields.iter(),
            cells: self.cells,
            cursor: 0,
            field_index: 0,
        }
    }
}

pub struct ObjectScalarCells<'fields, 'input> {
    fields: std::slice::Iter<'fields, FieldNode<'input>>,
    cells: &'fields [&'input [u8]],
    cursor: usize,
    field_index: usize,
}

impl<'input> Iterator for ObjectScalarCells<'_, 'input> {
    type Item = (usize, StringToken<'input>, &'input [u8]);

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            let field = self.fields.next()?;
            let field_index = self.field_index;
            self.field_index += 1;
            if field.children.is_empty() {
                let value = *self.cells.get(self.cursor)?;
                self.cursor += 1;
                return Some((field_index, field.name, value));
            }
            self.cursor += field.leaf_count();
        }
    }
}

pub struct ObjectSelectionResult<T> {
    pub selection: T,
    /// An immediate scalar field already consumed as structural metadata.
    /// The parser advances over its cell but does not emit it as a value.
    pub skip_field: Option<usize>,
}

impl<T> ObjectSelectionResult<T> {
    pub fn new(selection: T) -> Self {
        Self {
            selection,
            skip_field: None,
        }
    }
}

pub trait Consumer {
    type ObjectSelection: Default;

    /// Whether the next object plan needs scalar-field lookahead.
    fn needs_object_preflight(&self) -> bool {
        false
    }
    /// Offer scalar object fields before `start_object`. Typed tagged unions
    /// use this bounded lookahead to select a plan without buffering a value
    /// tree. Other consumers ignore it.
    fn object_scalar_hint(
        &mut self,
        key: StringToken<'_>,
        value: ScalarToken<'_>,
        at: Position,
    ) -> Result<(), Fault> {
        let _ = (key, value, at);
        Ok(())
    }
    /// Announce that every row of the array just started is emitted from one
    /// tabular header — an identical key/structure sequence per row, with
    /// `leaf_count` scalar cells. Consumers may resolve keys positionally for
    /// such rows; the default ignores the announcement.
    fn begin_tabular(&mut self, leaf_count: usize, at: Position) -> Result<(), Fault> {
        let _ = (leaf_count, at);
        Ok(())
    }
    fn start_object(&mut self, at: Position) -> Result<(), Fault>;
    /// Offer an adjacent object key and nested object opening as one
    /// operation. The default preserves the ordinary event sequence; typed
    /// consumers may carry the resolved child plan directly into frame setup.
    fn start_object_field(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault> {
        self.key(key, at)?;
        self.start_object(at)
    }
    /// Select the schema action for a nested field group before its object
    /// frame opens. The default keeps the ordinary key-then-object sequence.
    fn select_object_field(
        &mut self,
        key: StringToken<'_>,
        probe: ObjectProbe<'_, '_>,
        at: Position,
    ) -> Result<ObjectSelectionResult<Self::ObjectSelection>, Fault> {
        let _ = (key, probe, at);
        Ok(ObjectSelectionResult::new(Self::ObjectSelection::default()))
    }
    /// Open a nested field group using the result returned by
    /// `select_object_field` for this exact container.
    fn start_selected_object_field(
        &mut self,
        key: StringToken<'_>,
        selection: Self::ObjectSelection,
        at: Position,
    ) -> Result<(), Fault> {
        let _ = selection;
        self.start_object_field(key, at)
    }
    /// Close an object opened by `start_object_field`. The default preserves
    /// the ordinary event sequence; typed consumers may return a completed
    /// child directly to its known parent field.
    fn end_object_field(&mut self, at: Position) -> Result<(), Fault> {
        self.end_object(at)
    }
    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault>;
    /// Offer an adjacent object key and scalar as one operation. The default
    /// preserves the ordinary event sequence; typed consumers may fuse field
    /// resolution, scalar conversion, and placement without an awaiting-key
    /// state round-trip.
    fn scalar_field(
        &mut self,
        key: StringToken<'_>,
        value: ScalarToken<'_>,
        at: Position,
    ) -> Result<(), Fault> {
        self.key(key, at)?;
        self.scalar(value, at)
    }
    fn end_object(&mut self, at: Position) -> Result<(), Fault>;
    fn start_array(&mut self, declared_len: usize, at: Position) -> Result<(), Fault>;
    fn end_array(&mut self, at: Position) -> Result<(), Fault>;
    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault>;
}
