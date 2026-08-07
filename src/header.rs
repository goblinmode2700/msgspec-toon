//! Array header grammar: `key[N]{fields}:` with nested field groups.
//!
//! Nested field groups (`{a,b{c,d}}`) are TOON 4.0 core grammar, not an
//! extension: they are what keeps a record with a nested object on one row.

use crate::error::{Fault, FaultCode, Position};
use crate::event::StringToken;
use crate::scalar::{find_unquoted, scan_quoted, trim_spaces};

pub const DELIMITER: u8 = b',';

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

#[derive(Debug, Clone)]
pub struct Header<'a> {
    pub key: Option<StringToken<'a>>,
    pub declared_len: usize,
    pub fields: Vec<FieldNode<'a>>,
    pub inline_values: Option<&'a [u8]>,
}

impl Header<'_> {
    pub fn leaf_count(&self) -> usize {
        self.fields.iter().map(FieldNode::leaf_count).sum()
    }
}

/// Parse a content line as an array header. Returns `Ok(None)` when the line
/// is not a header (no unquoted `[` before any unquoted `:`).
pub fn parse_header<'a>(
    content: &'a [u8],
    strict: bool,
    at: Position,
) -> Result<Option<Header<'a>>, Fault> {
    let Some(bracket_start) = find_unquoted(content, b'[', 0) else {
        return Ok(None);
    };
    if let Some(colon) = find_unquoted(content, b':', 0)
        && colon < bracket_start
    {
        return Ok(None);
    }

    let bracket_end = find_unquoted(content, b']', bracket_start + 1)
        .ok_or(Fault::syntax_at(FaultCode::UnclosedBracket, at))?;

    let key = if bracket_start == 0 {
        None
    } else {
        Some(parse_string_token(trim_spaces(&content[..bracket_start]), at)?)
    };

    let length_digits = &content[bracket_start + 1..bracket_end];
    if length_digits.is_empty() || !length_digits.iter().all(u8::is_ascii_digit) {
        return Err(Fault::syntax(
            FaultCode::InvalidLength,
            at.line,
            Some(at.column + bracket_start as u32 + 1),
        ));
    }
    let declared_len: usize = std::str::from_utf8(length_digits)
        .ok()
        .and_then(|digits| digits.parse().ok())
        .ok_or(Fault::syntax_at(FaultCode::InvalidLength, at))?;

    let mut cursor = bracket_end + 1;
    let fields = if content.get(cursor) == Some(&b'{') {
        let close = find_matching_brace(content, cursor)
            .ok_or(Fault::syntax_at(FaultCode::UnclosedFieldGroup, at))?;
        let parsed = parse_field_group(&content[cursor + 1..close], strict, at)?;
        cursor = close + 1;
        parsed
    } else {
        Vec::new()
    };

    if content.get(cursor) != Some(&b':') {
        return Ok(None);
    }
    cursor += 1;

    let mut inline_values = &content[cursor..];
    if let Some((b' ', rest)) = inline_values.split_first() {
        inline_values = rest;
    }
    let inline_values = (!inline_values.is_empty()).then_some(inline_values);

    if !fields.is_empty() && inline_values.is_some() {
        return Err(Fault::syntax(
            FaultCode::ContentAfterFieldsHeader,
            at.line,
            Some(at.column + cursor as u32),
        ));
    }

    Ok(Some(Header { key, declared_len, fields, inline_values }))
}

pub fn parse_string_token<'a>(entry: &'a [u8], at: Position) -> Result<StringToken<'a>, Fault> {
    if entry.first() == Some(&b'"') {
        let (end, escaped) = scan_quoted(entry, 0, at)?;
        if end != entry.len() {
            return Err(Fault::syntax_at(FaultCode::ContentAfterFieldGroup, at));
        }
        Ok(StringToken::Quoted { inner: &entry[1..end - 1], escaped })
    } else {
        Ok(StringToken::Bare(entry))
    }
}

fn find_matching_brace(content: &[u8], open: usize) -> Option<usize> {
    debug_assert_eq!(content[open], b'{');
    let mut depth = 0usize;
    let mut in_quote = false;
    let mut index = open;
    while index < content.len() {
        let byte = content[index];
        if in_quote {
            if byte == b'\\' {
                index += 1;
            } else if byte == b'"' {
                in_quote = false;
            }
        } else {
            match byte {
                b'"' => in_quote = true,
                b'{' => depth += 1,
                b'}' => {
                    depth -= 1;
                    if depth == 0 {
                        return Some(index);
                    }
                }
                _ => {}
            }
        }
        index += 1;
    }
    None
}

fn parse_field_group<'a>(
    content: &'a [u8],
    strict: bool,
    at: Position,
) -> Result<Vec<FieldNode<'a>>, Fault> {
    let mut fields: Vec<FieldNode<'a>> = Vec::new();
    let mut cursor = 0usize;

    loop {
        let end = find_top_level_delimiter(content, cursor).unwrap_or(content.len());
        let entry = trim_spaces(&content[cursor..end]);
        if entry.is_empty() {
            return Err(Fault::syntax_at(FaultCode::EmptyField, at));
        }

        let (name, children) = match find_unquoted(entry, b'{', 0) {
            Some(group_start) => {
                let group_end = find_matching_brace(entry, group_start)
                    .ok_or(Fault::syntax_at(FaultCode::UnclosedFieldGroup, at))?;
                if group_end + 1 != entry.len() {
                    return Err(Fault::syntax_at(FaultCode::ContentAfterFieldGroup, at));
                }
                (
                    parse_string_token(trim_spaces(&entry[..group_start]), at)?,
                    parse_field_group(&entry[group_start + 1..group_end], strict, at)?,
                )
            }
            None => (parse_string_token(entry, at)?, Vec::new()),
        };

        if strict && fields.iter().any(|prior| token_bytes_eq(&prior.name, &name)) {
            return Err(Fault::syntax_at(FaultCode::DuplicateField, at));
        }
        fields.push(FieldNode { name, children });

        if end == content.len() {
            break;
        }
        cursor = end + 1;
    }

    Ok(fields)
}

/// Find the next field delimiter at brace depth zero, outside quotes.
fn find_top_level_delimiter(content: &[u8], from: usize) -> Option<usize> {
    let mut depth = 0usize;
    let mut in_quote = false;
    let mut index = from;
    while index < content.len() {
        let byte = content[index];
        if in_quote {
            if byte == b'\\' {
                index += 1;
            } else if byte == b'"' {
                in_quote = false;
            }
        } else {
            match byte {
                b'"' => in_quote = true,
                b'{' => depth += 1,
                b'}' => depth = depth.saturating_sub(1),
                _ if byte == DELIMITER && depth == 0 => return Some(index),
                _ => {}
            }
        }
        index += 1;
    }
    None
}

fn token_bytes_eq(left: &StringToken<'_>, right: &StringToken<'_>) -> bool {
    let raw = |token: &StringToken<'_>| match *token {
        StringToken::Bare(bytes) => bytes.to_vec(),
        StringToken::Quoted { inner, escaped } => {
            crate::scalar::unescape(inner, escaped).into_owned()
        }
    };
    raw(left) == raw(right)
}

#[cfg(test)]
mod tests {
    use super::*;

    const AT: Position = Position { line: 1, column: 1 };

    #[test]
    fn parses_nested_field_group_header() {
        let header = parse_header(b"workers[2]{pid,provider,metadata{alias,region}}:", true, AT)
            .unwrap()
            .unwrap();
        assert_eq!(header.declared_len, 2);
        assert_eq!(header.fields.len(), 3);
        assert_eq!(header.fields[2].children.len(), 2);
        assert_eq!(header.leaf_count(), 4);
        assert!(header.inline_values.is_none());
        assert!(matches!(header.key, Some(StringToken::Bare(b"workers"))));
    }

    #[test]
    fn parses_inline_array_header() {
        let header = parse_header(b"tags[3]: a,b,c", true, AT).unwrap().unwrap();
        assert_eq!(header.declared_len, 3);
        assert!(header.fields.is_empty());
        assert_eq!(header.inline_values, Some(&b"a,b,c"[..]));
    }

    #[test]
    fn parses_rootless_header() {
        let header = parse_header(b"[2]{a,b}:", true, AT).unwrap().unwrap();
        assert!(header.key.is_none());
        assert_eq!(header.leaf_count(), 2);
    }

    #[test]
    fn plain_key_value_is_not_a_header() {
        assert!(parse_header(b"name: value", true, AT).unwrap().is_none());
        assert!(parse_header(b"note: see [1]", true, AT).unwrap().is_none());
    }

    #[test]
    fn duplicate_fields_fail_in_strict() {
        let fault = parse_header(b"rows[1]{a,a}:", true, AT).unwrap_err();
        assert_eq!(fault.code, FaultCode::DuplicateField);
    }

    #[test]
    fn empty_array_header() {
        let header = parse_header(b"items[0]:", true, AT).unwrap().unwrap();
        assert_eq!(header.declared_len, 0);
        assert!(header.inline_values.is_none());
    }
}
