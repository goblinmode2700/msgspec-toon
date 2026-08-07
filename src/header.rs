//! Array header grammar: `key[N]{fields}:` with nested field groups, keyed
//! tabular headers `key[N:]{fields}:`, and per-header delimiters `[N|]`,
//! `[N\t]`, `[N:,]`, `[N:|]`, `[N:\t]`.
//!
//! Nested field groups (`{a,b{c,d}}`) are TOON 4.0 core grammar, not an
//! extension: they are what keeps a record with a nested object on one row.

use crate::error::{Fault, FaultCode, Position};
use crate::event::StringToken;
use crate::scalar::{find_unquoted, scan_quoted, trim_spaces};

pub const DEFAULT_DELIMITER: u8 = b',';

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
    pub keyed: bool,
    pub delimiter: u8,
    pub fields: Vec<FieldNode<'a>>,
    pub inline_values: Option<&'a [u8]>,
}

impl Header<'_> {
    pub fn leaf_count(&self) -> usize {
        self.fields.iter().map(FieldNode::leaf_count).sum()
    }
}

/// The three-way outcome the parser needs: not a header at all (an ordinary
/// key/value line), a well-formed header, or a malformed header — which is a
/// strict-mode error and a key-value fall-through in non-strict mode.
#[derive(Debug)]
pub enum HeaderOutcome<'a> {
    NotHeader,
    Header(Header<'a>),
    Malformed(FaultCode),
}

pub fn parse_header<'a>(
    content: &'a [u8],
    strict: bool,
    at: Position,
) -> Result<HeaderOutcome<'a>, Fault> {
    let Some(bracket_start) = find_unquoted(content, b'[', 0) else {
        return Ok(HeaderOutcome::NotHeader);
    };
    if let Some(colon) = find_unquoted(content, b':', 0)
        && colon < bracket_start
    {
        return Ok(HeaderOutcome::NotHeader);
    }

    // Whitespace between a key and its bracket segment is malformed.
    if bracket_start > 0 && content[bracket_start - 1] == b' ' {
        return Ok(HeaderOutcome::Malformed(FaultCode::MalformedHeader));
    }

    let Some(bracket_end) = find_unquoted(content, b']', bracket_start + 1) else {
        return Ok(HeaderOutcome::Malformed(FaultCode::UnclosedBracket));
    };

    let Some((declared_len, keyed, delimiter)) =
        parse_bracket(&content[bracket_start + 1..bracket_end])
    else {
        return Ok(HeaderOutcome::Malformed(FaultCode::InvalidLength));
    };

    let key = if bracket_start == 0 {
        None
    } else {
        Some(parse_string_token(&content[..bracket_start], at)?)
    };

    let mut cursor = bracket_end + 1;
    let fields = if content.get(cursor) == Some(&b'{') {
        let Some(close) = find_matching_brace(content, cursor) else {
            return Ok(HeaderOutcome::Malformed(FaultCode::UnclosedFieldGroup));
        };
        let parsed = match parse_field_group(&content[cursor + 1..close], delimiter, strict, at) {
            Ok(parsed) => parsed,
            Err(code) => return Ok(HeaderOutcome::Malformed(code)),
        };
        cursor = close + 1;
        parsed
    } else {
        Vec::new()
    };

    if content.get(cursor) != Some(&b':') {
        // Junk between the bracket segment (or field group) and the colon.
        return Ok(HeaderOutcome::Malformed(FaultCode::MalformedHeader));
    }
    cursor += 1;

    let mut inline_values = &content[cursor..];
    if let Some((b' ', rest)) = inline_values.split_first() {
        inline_values = rest;
    }
    let inline_values = (!inline_values.is_empty()).then_some(inline_values);

    if !fields.is_empty() && inline_values.is_some() {
        return Ok(HeaderOutcome::Malformed(
            FaultCode::ContentAfterFieldsHeader,
        ));
    }
    if keyed && fields.is_empty() {
        return Ok(HeaderOutcome::Malformed(FaultCode::MalformedHeader));
    }

    Ok(HeaderOutcome::Header(Header {
        key,
        declared_len,
        keyed,
        delimiter,
        fields,
        inline_values,
    }))
}

/// Parse the inside of the bracket: `N`, `N:`, `N<d>`, or `N:<d>` where `<d>`
/// is one of tab, pipe, comma. Leading-zero lengths are malformed.
fn parse_bracket(content: &[u8]) -> Option<(usize, bool, u8)> {
    let digit_count = content
        .iter()
        .take_while(|byte| byte.is_ascii_digit())
        .count();
    if digit_count == 0 {
        return None;
    }
    let digits = &content[..digit_count];
    if digits.len() > 1 && digits[0] == b'0' {
        return None;
    }
    let declared_len: usize = std::str::from_utf8(digits)
        .ok()
        .and_then(|text| text.parse().ok())?;

    let mut cursor = digit_count;
    let keyed = content.get(cursor) == Some(&b':');
    cursor += usize::from(keyed);
    // The comma is the default and its explicit spelling is invalid.
    let delimiter = match content.get(cursor) {
        Some(&byte @ (b'\t' | b'|')) => {
            cursor += 1;
            byte
        }
        _ => DEFAULT_DELIMITER,
    };
    (cursor == content.len()).then_some((declared_len, keyed, delimiter))
}

pub fn parse_string_token<'a>(entry: &'a [u8], at: Position) -> Result<StringToken<'a>, Fault> {
    if entry.first() == Some(&b'"') {
        let (end, escaped) = scan_quoted(entry, 0, at)?;
        if end != entry.len() {
            return Err(Fault::syntax_at(FaultCode::ContentAfterFieldGroup, at));
        }
        Ok(StringToken::Quoted {
            inner: &entry[1..end - 1],
            escaped,
        })
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
    delimiter: u8,
    strict: bool,
    at: Position,
) -> Result<Vec<FieldNode<'a>>, FaultCode> {
    let mut fields: Vec<FieldNode<'a>> = Vec::new();
    let mut cursor = 0usize;

    loop {
        let end = find_top_level_delimiter(content, cursor, delimiter).unwrap_or(content.len());
        let entry = trim_spaces(&content[cursor..end]);
        if entry.is_empty() {
            return Err(FaultCode::EmptyField);
        }

        let (name, children) = match find_unquoted(entry, b'{', 0) {
            Some(group_start) => {
                let Some(group_end) = find_matching_brace(entry, group_start) else {
                    return Err(FaultCode::UnclosedFieldGroup);
                };
                if group_end + 1 != entry.len() {
                    return Err(FaultCode::ContentAfterFieldGroup);
                }
                (
                    parse_string_token(trim_spaces(&entry[..group_start]), at)
                        .map_err(|fault| fault.code)?,
                    parse_field_group(&entry[group_start + 1..group_end], delimiter, strict, at)?,
                )
            }
            None => (
                parse_string_token(entry, at).map_err(|fault| fault.code)?,
                Vec::new(),
            ),
        };

        // Duplicate field names: strict rejects; non-strict resolves
        // last-write-wins downstream, so both fields are kept and the
        // consumer's key overwrite provides the mandated behavior.
        if strict
            && fields
                .iter()
                .any(|prior| token_bytes_eq(&prior.name, &name))
        {
            return Err(FaultCode::DuplicateField);
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
fn find_top_level_delimiter(content: &[u8], from: usize, delimiter: u8) -> Option<usize> {
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
                _ if byte == delimiter && depth == 0 => return Some(index),
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

    fn header(content: &[u8]) -> Header<'_> {
        match parse_header(content, true, AT).unwrap() {
            HeaderOutcome::Header(header) => header,
            other => panic!("expected header, got {other:?}"),
        }
    }

    fn malformed(content: &[u8]) -> FaultCode {
        match parse_header(content, true, AT).unwrap() {
            HeaderOutcome::Malformed(code) => code,
            other => panic!("expected malformed, got {other:?}"),
        }
    }

    #[test]
    fn parses_nested_field_group_header() {
        let parsed = header(b"workers[2]{pid,provider,metadata{alias,region}}:");
        assert_eq!(parsed.declared_len, 2);
        assert_eq!(parsed.fields.len(), 3);
        assert_eq!(parsed.fields[2].children.len(), 2);
        assert_eq!(parsed.leaf_count(), 4);
        assert!(!parsed.keyed);
        assert!(parsed.inline_values.is_none());
        assert!(matches!(parsed.key, Some(StringToken::Bare(b"workers"))));
    }

    #[test]
    fn parses_inline_array_header() {
        let parsed = header(b"tags[3]: a,b,c");
        assert_eq!(parsed.declared_len, 3);
        assert!(parsed.fields.is_empty());
        assert_eq!(parsed.inline_values, Some(&b"a,b,c"[..]));
    }

    #[test]
    fn parses_delimiter_headers() {
        let parsed = header(b"tags[3|]: reading|gaming|coding");
        assert_eq!(parsed.delimiter, b'|');
        let parsed = header(b"tags[3\t]: a\tb\tc");
        assert_eq!(parsed.delimiter, b'\t');
        let parsed = header(b"orders[2|]{id|customer{name|country}|total}:");
        assert_eq!(parsed.leaf_count(), 4);
    }

    #[test]
    fn parses_keyed_headers() {
        let parsed = header(b"servers[2:]{host,port}:");
        assert!(parsed.keyed);
        assert_eq!(parsed.declared_len, 2);
        assert_eq!(parsed.fields.len(), 2);
        let parsed = header(b"servers[2:|]{host|port}:");
        assert!(parsed.keyed);
        assert_eq!(parsed.delimiter, b'|');
        let parsed = header(b"[2:]{age,city}:");
        assert!(parsed.keyed);
        assert!(parsed.key.is_none());
    }

    #[test]
    fn plain_key_value_is_not_a_header() {
        assert!(matches!(
            parse_header(b"name: value", true, AT).unwrap(),
            HeaderOutcome::NotHeader
        ));
        assert!(matches!(
            parse_header(b"note: see [1]", true, AT).unwrap(),
            HeaderOutcome::NotHeader
        ));
    }

    #[test]
    fn malformed_headers_are_reported_not_guessed() {
        assert_eq!(malformed(b"key[]: 1,2"), FaultCode::InvalidLength);
        assert_eq!(malformed(b"foo[bar][1]: 20"), FaultCode::InvalidLength);
        assert_eq!(malformed(b"items[03]: a,b,c"), FaultCode::InvalidLength);
        assert_eq!(malformed(b"foo [2]: bar,baz"), FaultCode::MalformedHeader);
        assert_eq!(malformed(b"foo[1][bar]: 10"), FaultCode::MalformedHeader);
        assert_eq!(malformed(b"foo[2]extra: a,b"), FaultCode::MalformedHeader);
        assert_eq!(malformed(b"rows[1]{a,a}:"), FaultCode::DuplicateField);
        assert_eq!(malformed(b"k[2:]:"), FaultCode::MalformedHeader);
    }

    #[test]
    fn empty_array_header() {
        let parsed = header(b"items[0]:");
        assert_eq!(parsed.declared_len, 0);
        assert!(parsed.inline_values.is_none());
    }
}
