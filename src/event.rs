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

pub trait Consumer {
    /// Announce that every row of the array just started is emitted from one
    /// tabular header — an identical key/structure sequence per row, with
    /// `leaf_count` scalar cells. Consumers may resolve keys positionally for
    /// such rows; the default ignores the announcement.
    fn begin_tabular(&mut self, leaf_count: usize, at: Position) -> Result<(), Fault> {
        let _ = (leaf_count, at);
        Ok(())
    }
    fn start_object(&mut self, at: Position) -> Result<(), Fault>;
    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault>;
    fn end_object(&mut self, at: Position) -> Result<(), Fault>;
    fn start_array(&mut self, declared_len: usize, at: Position) -> Result<(), Fault>;
    fn end_array(&mut self, at: Position) -> Result<(), Fault>;
    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault>;
}
