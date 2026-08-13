//! The untyped consumer: builds ordinary dict/list values for `type=Any`.
//!
//! Its containers are the builtin tree: requested output when the caller asked
//! for `Any`, and the intermediate tree the wrapper pipeline pays for when the
//! caller wanted a Struct. Both are built through `containers.rs`, which is
//! what makes the G2 count independent of this module.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString};
use rustc_hash::FxHashMap;

use crate::containers::{new_builtin_dict, new_builtin_list};
use crate::error::{Fault, FaultCode, Position};
use crate::event::{Consumer, ScalarToken, StringToken};
use crate::limits::reserve_elements;
use crate::pyval::scalar_to_py;

#[derive(Hash, PartialEq, Eq)]
struct BorrowedKeyCacheKey {
    /// Borrowed input and header slices remain stable for the complete decode.
    /// Their address is only an identity token; it is never dereferenced here.
    address: usize,
    len: usize,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum KeyCacheMode {
    None,
    Tabular,
    RepeatedRecord,
}

enum Builder<'py> {
    Dict {
        map: Bound<'py, PyDict>,
        pending_key: Option<Bound<'py, PyAny>>,
    },
    List {
        items: Vec<Bound<'py, PyAny>>,
    },
}

pub struct UntypedConsumer<'py> {
    py: Python<'py>,
    float_hook: Option<Py<PyAny>>,
    stack: Vec<Builder<'py>>,
    result: Option<Bound<'py, PyAny>>,
    pub pending_err: Option<PyErr>,
    /// Optimization D3: tabular rows repeat the same borrowed header slices
    /// thousands of times. Address identity avoids hashing their contents.
    borrowed_key_cache: FxHashMap<BorrowedKeyCacheKey, Py<PyString>>,
    /// Ordinary records repeat spellings at different input addresses, and
    /// escaped tabular keys own their unescaped bytes. A separate content map
    /// permits borrowed `[u8]` hash lookup instead of scanning the address-keyed
    /// cache. It is decoder-local and therefore bounded by one decode call,
    /// though the number of entries within that call is intentionally unbounded.
    content_key_cache: FxHashMap<Vec<u8>, Py<PyString>>,
    key_cache_mode: KeyCacheMode,
    repeated_objects_seen: u8,
}

impl<'py> UntypedConsumer<'py> {
    pub fn new(py: Python<'py>, float_hook: Option<Py<PyAny>>) -> Self {
        Self {
            py,
            float_hook,
            stack: Vec::new(),
            result: None,
            pending_err: None,
            borrowed_key_cache: FxHashMap::default(),
            content_key_cache: FxHashMap::default(),
            key_cache_mode: KeyCacheMode::None,
            repeated_objects_seen: 0,
        }
    }

    pub fn take_result(&mut self) -> Option<Bound<'py, PyAny>> {
        self.result.take()
    }

    pub fn is_complete(&self) -> bool {
        self.stack.is_empty() && self.result.is_some()
    }

    fn internal(&mut self, err: PyErr, at: Position) -> Fault {
        self.pending_err = Some(err);
        Fault::syntax_at(FaultCode::Internal, at)
    }

    fn place(&mut self, value: Bound<'py, PyAny>, at: Position) -> Result<(), Fault> {
        match self.stack.last_mut() {
            Some(Builder::Dict { map, pending_key }) => {
                let key = pending_key
                    .take()
                    .ok_or(Fault::syntax_at(FaultCode::Internal, at))?;
                map.set_item(key, value)
                    .map_err(|err| self.internal(err, at))?;
            }
            Some(Builder::List { items }) => items.push(value),
            None => self.result = Some(value),
        }
        Ok(())
    }

    #[inline(never)]
    fn key_to_py(&mut self, key: StringToken<'_>) -> Bound<'py, PyAny> {
        let bytes = match key {
            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
            StringToken::Quoted { inner, escaped } => crate::scalar::unescape(inner, escaped),
        };
        if self.key_cache_mode == KeyCacheMode::None {
            // Root entry objects usually have unique keys. Keep their adopted
            // allocation-free path instead of populating a cache that cannot
            // produce a hit.
            let text = unsafe { std::str::from_utf8_unchecked(&bytes) };
            return PyString::new(self.py, text).into_any();
        }
        match bytes {
            std::borrow::Cow::Borrowed(bytes) => {
                let cache_key = BorrowedKeyCacheKey {
                    address: bytes.as_ptr() as usize,
                    len: bytes.len(),
                };
                if let Some(cached) = self.borrowed_key_cache.get(&cache_key) {
                    return cached.bind(self.py).to_owned().into_any();
                }
                // SAFETY: parsing begins with whole-document UTF-8 validation.
                let text = unsafe { std::str::from_utf8_unchecked(bytes) };
                let created = PyString::new(self.py, text);
                self.borrowed_key_cache
                    .insert(cache_key, created.clone().unbind());
                created.into_any()
            }
            std::borrow::Cow::Owned(bytes) => {
                if let Some(cached) = self.content_key_cache.get(bytes.as_slice()) {
                    return cached.bind(self.py).to_owned().into_any();
                }
                // SAFETY: `unescape` rejects escapes that cannot produce valid UTF-8.
                let text = unsafe { std::str::from_utf8_unchecked(&bytes) };
                let created = PyString::new(self.py, text);
                self.content_key_cache
                    .insert(bytes, created.clone().unbind());
                created.into_any()
            }
        }
    }

    /// Nested ordinary objects repeat key spellings at different source
    /// addresses. Look up their bytes by content in average O(1); the
    /// root-entry and tabular borrowed-key paths never call this helper.
    #[inline(never)]
    fn cached_ordinary_key(&mut self, key: StringToken<'_>) -> Bound<'py, PyAny> {
        let bytes = match key {
            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
            StringToken::Quoted { inner, escaped } => crate::scalar::unescape(inner, escaped),
        };
        if let Some(cached) = self.content_key_cache.get(bytes.as_ref()) {
            return cached.bind(self.py).to_owned().into_any();
        }
        // SAFETY: parsing begins with whole-document UTF-8 validation, and
        // `unescape` rejects escapes that cannot produce invalid UTF-8.
        let text = unsafe { std::str::from_utf8_unchecked(&bytes) };
        let created = PyString::new(self.py, text);
        self.content_key_cache
            .insert(bytes.into_owned(), created.clone().unbind());
        created.into_any()
    }
}

impl Consumer for UntypedConsumer<'_> {
    type ObjectSelection = ();

    fn begin_tabular(&mut self, _leaf_count: usize, _at: Position) -> Result<(), Fault> {
        self.key_cache_mode = KeyCacheMode::Tabular;
        Ok(())
    }

    fn start_object(&mut self, _at: Position) -> Result<(), Fault> {
        self.stack.push(Builder::Dict {
            map: new_builtin_dict(self.py),
            pending_key: None,
        });
        Ok(())
    }

    fn start_repeated_object(
        &mut self,
        _selection: Self::ObjectSelection,
        _at: Position,
    ) -> Result<(), Fault> {
        self.repeated_objects_seen = self.repeated_objects_seen.saturating_add(1);
        if self.repeated_objects_seen > 8 {
            self.key_cache_mode = KeyCacheMode::RepeatedRecord;
        }
        self.start_object(_at)
    }

    #[inline(always)]
    fn key(&mut self, key: StringToken<'_>, at: Position) -> Result<(), Fault> {
        let key = if self.key_cache_mode == KeyCacheMode::None {
            self.uncached_key(key)
        } else if self.key_cache_mode == KeyCacheMode::RepeatedRecord {
            self.cached_ordinary_key(key)
        } else if self.stack.len() == 1 {
            self.uncached_key(key)
        } else {
            self.key_to_py(key)
        };
        match self.stack.last_mut() {
            Some(Builder::Dict { pending_key, .. }) => {
                *pending_key = Some(key);
                Ok(())
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn end_object(&mut self, at: Position) -> Result<(), Fault> {
        match self.stack.pop() {
            Some(Builder::Dict { map, .. }) => self.place(map.into_any(), at),
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn start_array(&mut self, declared_len: usize, _at: Position) -> Result<(), Fault> {
        self.stack.push(Builder::List {
            items: Vec::with_capacity(reserve_elements(declared_len)),
        });
        Ok(())
    }

    fn end_array(&mut self, at: Position) -> Result<(), Fault> {
        match self.stack.pop() {
            Some(Builder::List { items }) => {
                let list =
                    new_builtin_list(self.py, items).map_err(|err| self.internal(err, at))?;
                self.place(list.into_any(), at)
            }
            _ => Err(Fault::syntax_at(FaultCode::Internal, at)),
        }
    }

    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault> {
        let converted = scalar_to_py(self.py, token, self.float_hook.as_ref());
        let value = match converted {
            Ok(value) => value,
            Err(err) => return Err(self.internal(err, at)),
        };
        self.place(value, at)
    }
}

impl<'py> UntypedConsumer<'py> {
    #[inline(never)]
    fn uncached_key(&self, key: StringToken<'_>) -> Bound<'py, PyAny> {
        let bytes = match key {
            StringToken::Bare(bytes) => std::borrow::Cow::Borrowed(bytes),
            StringToken::Quoted { inner, escaped } => crate::scalar::unescape(inner, escaped),
        };
        // SAFETY: parsing begins with whole-document UTF-8 validation, and
        // `unescape` rejects escapes that cannot produce valid UTF-8.
        let text = unsafe { std::str::from_utf8_unchecked(&bytes) };
        PyString::new(self.py, text).into_any()
    }
}
