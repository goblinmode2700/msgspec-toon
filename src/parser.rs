//! Structural parser: drives a `Consumer` from scanned lines.
//!
//! Supported document grammar (the Tier 0 / challenge-shaped subset of TOON
//! 4.1): root objects, root arrays, root scalars, nested objects by
//! indentation, inline scalar arrays `key[N]: a,b,c`, tabular arrays with
//! nested field groups, and list arrays with `- ` items (scalar or object).

use crate::error::{Fault, FaultCode, Position};
use crate::event::{Consumer, ScalarToken, StringToken};
use crate::header::{FieldNode, Header, parse_header, parse_string_token};
use crate::scalar::{
    classify_bare, find_unquoted, scan_quoted, split_cells, trim_spaces, unescape,
};
use crate::scan::Lines;

pub fn parse<C: Consumer>(input: &[u8], strict: bool, consumer: &mut C) -> Result<(), Fault> {
    if std::str::from_utf8(input).is_err() {
        return Err(Fault::syntax(FaultCode::InvalidUtf8, 1, None));
    }

    let mut lines = Lines::new(input, strict);
    let Some(first) = lines.peek()? else {
        let at = Position { line: 1, column: 1 };
        consumer.start_object(at)?;
        consumer.end_object(at)?;
        return Ok(());
    };
    if first.depth != 0 {
        return Err(Fault::syntax_at(FaultCode::InvalidIndent, first.position));
    }

    let at = first.position;
    if let Some(header) = parse_header(first.content, strict, at)? {
        if header.key.is_none() {
            lines.advance()?;
            parse_array_body(&mut lines, &header, 0, at, strict, consumer)?;
            expect_end(&mut lines)?;
            return Ok(());
        }
        consumer.start_object(at)?;
        parse_object_body(&mut lines, 0, None, strict, consumer)?;
        consumer.end_object(at)?;
        return Ok(());
    }

    if entry_colon(first.content).is_some() {
        consumer.start_object(at)?;
        parse_object_body(&mut lines, 0, None, strict, consumer)?;
        consumer.end_object(at)?;
        return Ok(());
    }

    // Root scalar.
    lines.advance()?;
    consumer.scalar(classify_value(first.content, at)?, at)?;
    expect_end(&mut lines)?;
    Ok(())
}

fn expect_end(lines: &mut Lines<'_>) -> Result<(), Fault> {
    match lines.peek()? {
        Some(line) => Err(Fault::syntax_at(FaultCode::TrailingContent, line.position)),
        None => Ok(()),
    }
}

/// The first unquoted colon that ends the line or is followed by a space —
/// i.e. a key/value separator rather than a colon inside a bare value.
fn entry_colon(content: &[u8]) -> Option<usize> {
    let index = find_unquoted(content, b':', 0)?;
    (index + 1 == content.len() || content[index + 1] == b' ').then_some(index)
}

fn classify_value<'a>(value: &'a [u8], at: Position) -> Result<ScalarToken<'a>, Fault> {
    if value.first() == Some(&b'"') {
        let (end, escaped) = scan_quoted(value, 0, at)?;
        if end != value.len() {
            return Err(Fault::syntax(
                FaultCode::TrailingContent,
                at.line,
                Some(at.column + end as u32),
            ));
        }
        Ok(ScalarToken::Quoted {
            inner: &value[1..end - 1],
            escaped,
        })
    } else {
        Ok(classify_bare(value))
    }
}

fn token_owned_bytes(token: &StringToken<'_>) -> Vec<u8> {
    match *token {
        StringToken::Bare(bytes) => bytes.to_vec(),
        StringToken::Quoted { inner, escaped } => unescape(inner, escaped).into_owned(),
    }
}

fn parse_object_body<C: Consumer>(
    lines: &mut Lines<'_>,
    depth: usize,
    first: Option<(&[u8], Position)>,
    strict: bool,
    consumer: &mut C,
) -> Result<(), Fault> {
    let mut seen: Vec<Vec<u8>> = Vec::new();

    if let Some((content, at)) = first {
        parse_entry(content, at, lines, depth, strict, consumer, &mut seen)?;
    }
    loop {
        let Some(line) = lines.peek()? else {
            return Ok(());
        };
        if line.depth < depth {
            return Ok(());
        }
        if line.depth > depth {
            return Err(Fault::syntax_at(FaultCode::DepthJump, line.position));
        }
        lines.advance()?;
        parse_entry(
            line.content,
            line.position,
            lines,
            depth,
            strict,
            consumer,
            &mut seen,
        )?;
    }
}

#[allow(clippy::too_many_arguments)]
fn parse_entry<C: Consumer>(
    content: &[u8],
    at: Position,
    lines: &mut Lines<'_>,
    depth: usize,
    strict: bool,
    consumer: &mut C,
    seen: &mut Vec<Vec<u8>>,
) -> Result<(), Fault> {
    if let Some(header) = parse_header(content, strict, at)? {
        let key = header
            .key
            .ok_or(Fault::syntax_at(FaultCode::ExpectedKey, at))?;
        note_key(&key, at, strict, seen)?;
        consumer.key(key, at)?;
        return parse_array_body(lines, &header, depth, at, strict, consumer);
    }

    let Some(colon) = entry_colon(content) else {
        return Err(Fault::syntax_at(FaultCode::ExpectedKey, at));
    };
    let key = parse_string_token(trim_spaces(&content[..colon]), at)?;
    note_key(&key, at, strict, seen)?;

    let rest = &content[colon + 1..];
    if rest.is_empty() {
        consumer.key(key, at)?;
        let nested = match lines.peek()? {
            Some(line) if line.depth > depth => {
                if line.depth != depth + 1 {
                    return Err(Fault::syntax_at(FaultCode::DepthJump, line.position));
                }
                true
            }
            _ => false,
        };
        consumer.start_object(at)?;
        if nested {
            parse_object_body(lines, depth + 1, None, strict, consumer)?;
        }
        consumer.end_object(at)?;
        return Ok(());
    }

    let value_at = Position {
        line: at.line,
        column: at.column + colon as u32 + 2,
    };
    consumer.key(key, at)?;
    consumer.scalar(classify_value(&rest[1..], value_at)?, value_at)?;
    Ok(())
}

fn note_key(
    key: &StringToken<'_>,
    at: Position,
    strict: bool,
    seen: &mut Vec<Vec<u8>>,
) -> Result<(), Fault> {
    if !strict {
        return Ok(());
    }
    let owned = token_owned_bytes(key);
    if seen.contains(&owned) {
        return Err(Fault::syntax_at(FaultCode::DuplicateKey, at));
    }
    seen.push(owned);
    Ok(())
}

fn parse_array_body<C: Consumer>(
    lines: &mut Lines<'_>,
    header: &Header<'_>,
    depth: usize,
    at: Position,
    strict: bool,
    consumer: &mut C,
) -> Result<(), Fault> {
    consumer.start_array(header.declared_len, at)?;

    if !header.fields.is_empty() {
        let leaf_count = header.leaf_count();
        for _ in 0..header.declared_len {
            let row = match lines.peek()? {
                Some(line) if line.depth == depth + 1 => {
                    lines.advance()?;
                    line
                }
                Some(line) => {
                    return Err(Fault::syntax_at(FaultCode::WrongArrayLength, line.position));
                }
                None => {
                    return Err(Fault::syntax(
                        FaultCode::WrongArrayLength,
                        lines.current_line_number(),
                        None,
                    ));
                }
            };
            let cells = split_cells(row.content, crate::header::DELIMITER);
            if cells.len() != leaf_count {
                return Err(Fault::syntax_at(FaultCode::WrongRowWidth, row.position));
            }
            consumer.start_object(row.position)?;
            let mut cursor = 0usize;
            emit_row_fields(&header.fields, &cells, &mut cursor, row.position, consumer)?;
            consumer.end_object(row.position)?;
        }
        reject_extra_rows(lines, depth)?;
    } else if let Some(inline) = header.inline_values {
        let cells = split_cells(inline, crate::header::DELIMITER);
        if cells.len() != header.declared_len {
            return Err(Fault::syntax_at(FaultCode::WrongArrayLength, at));
        }
        for cell in cells {
            consumer.scalar(classify_value(cell, at)?, at)?;
        }
    } else {
        for _ in 0..header.declared_len {
            let item = match lines.peek()? {
                Some(line) if line.depth == depth + 1 => {
                    lines.advance()?;
                    line
                }
                Some(line) => {
                    return Err(Fault::syntax_at(FaultCode::WrongArrayLength, line.position));
                }
                None => {
                    return Err(Fault::syntax(
                        FaultCode::WrongArrayLength,
                        lines.current_line_number(),
                        None,
                    ));
                }
            };
            parse_list_item(item.content, item.position, lines, depth, strict, consumer)?;
        }
        reject_extra_rows(lines, depth)?;
    }

    consumer.end_array(at)?;
    Ok(())
}

fn reject_extra_rows(lines: &mut Lines<'_>, depth: usize) -> Result<(), Fault> {
    if let Some(line) = lines.peek()?
        && line.depth > depth
    {
        return Err(Fault::syntax_at(FaultCode::WrongArrayLength, line.position));
    }
    Ok(())
}

fn emit_row_fields<C: Consumer>(
    fields: &[FieldNode<'_>],
    cells: &[&[u8]],
    cursor: &mut usize,
    at: Position,
    consumer: &mut C,
) -> Result<(), Fault> {
    for node in fields {
        consumer.key(node.name, at)?;
        if node.children.is_empty() {
            consumer.scalar(classify_value(cells[*cursor], at)?, at)?;
            *cursor += 1;
        } else {
            consumer.start_object(at)?;
            emit_row_fields(&node.children, cells, cursor, at, consumer)?;
            consumer.end_object(at)?;
        }
    }
    Ok(())
}

fn parse_list_item<C: Consumer>(
    content: &[u8],
    at: Position,
    lines: &mut Lines<'_>,
    depth: usize,
    strict: bool,
    consumer: &mut C,
) -> Result<(), Fault> {
    if content == b"-" {
        consumer.start_object(at)?;
        consumer.end_object(at)?;
        return Ok(());
    }
    let Some(item) = content.strip_prefix(b"- ") else {
        return Err(Fault::syntax_at(FaultCode::MissingListItem, at));
    };
    let item_at = Position {
        line: at.line,
        column: at.column + 2,
    };

    if let Some(header) = parse_header(item, strict, item_at)? {
        if header.key.is_none() {
            // An anonymous nested array item: `- [2]: 1,2`.
            return parse_array_body(lines, &header, depth + 1, item_at, strict, consumer);
        }
        // An object item whose first entry is an array.
        consumer.start_object(item_at)?;
        let mut seen = vec![token_owned_bytes(header.key.as_ref().unwrap())];
        consumer.key(header.key.unwrap(), item_at)?;
        parse_array_body(lines, &header, depth + 1, item_at, strict, consumer)?;
        continue_object_item(lines, depth, strict, consumer, &mut seen)?;
        consumer.end_object(item_at)?;
        return Ok(());
    }

    if entry_colon(item).is_some() {
        // An object item: first key/value on the dash line, the rest two
        // levels deeper (the `- ` prefix occupies one indent unit).
        consumer.start_object(item_at)?;
        let mut seen = Vec::new();
        parse_entry(item, item_at, lines, depth + 2, strict, consumer, &mut seen)?;
        continue_object_item(lines, depth, strict, consumer, &mut seen)?;
        consumer.end_object(item_at)?;
        return Ok(());
    }

    consumer.scalar(classify_value(item, item_at)?, item_at)?;
    Ok(())
}

fn continue_object_item<C: Consumer>(
    lines: &mut Lines<'_>,
    depth: usize,
    strict: bool,
    consumer: &mut C,
    seen: &mut Vec<Vec<u8>>,
) -> Result<(), Fault> {
    loop {
        let Some(line) = lines.peek()? else {
            return Ok(());
        };
        if line.depth != depth + 2 {
            return Ok(());
        }
        lines.advance()?;
        parse_entry(
            line.content,
            line.position,
            lines,
            depth + 2,
            strict,
            consumer,
            seen,
        )?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, PartialEq)]
    enum Ev {
        So,
        Eo,
        Sa(usize),
        Ea,
        Key(Vec<u8>),
        Scalar(String),
    }

    #[derive(Default)]
    struct Recorder {
        events: Vec<Ev>,
    }

    impl Consumer for Recorder {
        fn start_object(&mut self, _at: Position) -> Result<(), Fault> {
            self.events.push(Ev::So);
            Ok(())
        }
        fn key(&mut self, key: StringToken<'_>, _at: Position) -> Result<(), Fault> {
            self.events.push(Ev::Key(token_owned_bytes(&key)));
            Ok(())
        }
        fn end_object(&mut self, _at: Position) -> Result<(), Fault> {
            self.events.push(Ev::Eo);
            Ok(())
        }
        fn start_array(&mut self, declared_len: usize, _at: Position) -> Result<(), Fault> {
            self.events.push(Ev::Sa(declared_len));
            Ok(())
        }
        fn end_array(&mut self, _at: Position) -> Result<(), Fault> {
            self.events.push(Ev::Ea);
            Ok(())
        }
        fn scalar(&mut self, token: ScalarToken<'_>, _at: Position) -> Result<(), Fault> {
            let text = match token {
                ScalarToken::Null => "null".to_string(),
                ScalarToken::Bool(value) => value.to_string(),
                ScalarToken::Integer(bytes) => {
                    format!("i:{}", std::str::from_utf8(bytes).unwrap())
                }
                ScalarToken::Float(bytes) => format!("f:{}", std::str::from_utf8(bytes).unwrap()),
                ScalarToken::BareString(bytes) => {
                    format!("s:{}", std::str::from_utf8(bytes).unwrap())
                }
                ScalarToken::Quoted { inner, escaped } => format!(
                    "q:{}",
                    String::from_utf8(unescape(inner, escaped).into_owned()).unwrap()
                ),
            };
            self.events.push(Ev::Scalar(text));
            Ok(())
        }
    }

    fn run(input: &[u8]) -> Vec<Ev> {
        let mut recorder = Recorder::default();
        parse(input, true, &mut recorder).unwrap();
        recorder.events
    }

    fn run_err(input: &[u8]) -> Fault {
        let mut recorder = Recorder::default();
        parse(input, true, &mut recorder).unwrap_err()
    }

    #[test]
    fn parses_challenge_shape() {
        let events = run(
            b"workers[2]{pid,provider,metadata{alias,region}}:\n  20324,claude,worker-a,west\n  80916,claude,worker-b,east",
        );
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"workers".to_vec()),
                Ev::Sa(2),
                Ev::So,
                Ev::Key(b"pid".to_vec()),
                Ev::Scalar("i:20324".into()),
                Ev::Key(b"provider".to_vec()),
                Ev::Scalar("s:claude".into()),
                Ev::Key(b"metadata".to_vec()),
                Ev::So,
                Ev::Key(b"alias".to_vec()),
                Ev::Scalar("s:worker-a".into()),
                Ev::Key(b"region".to_vec()),
                Ev::Scalar("s:west".into()),
                Ev::Eo,
                Ev::Eo,
                Ev::So,
                Ev::Key(b"pid".to_vec()),
                Ev::Scalar("i:80916".into()),
                Ev::Key(b"provider".to_vec()),
                Ev::Scalar("s:claude".into()),
                Ev::Key(b"metadata".to_vec()),
                Ev::So,
                Ev::Key(b"alias".to_vec()),
                Ev::Scalar("s:worker-b".into()),
                Ev::Key(b"region".to_vec()),
                Ev::Scalar("s:east".into()),
                Ev::Eo,
                Ev::Eo,
                Ev::Ea,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn parses_nested_object_and_inline_array() {
        let events = run(b"name: demo\nnested:\n  tags[2]: a,b");
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"name".to_vec()),
                Ev::Scalar("s:demo".into()),
                Ev::Key(b"nested".to_vec()),
                Ev::So,
                Ev::Key(b"tags".to_vec()),
                Ev::Sa(2),
                Ev::Scalar("s:a".into()),
                Ev::Scalar("s:b".into()),
                Ev::Ea,
                Ev::Eo,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn parses_list_array_with_object_items() {
        let events = run(b"data[2]:\n  - pid: 1\n    name: a\n  - pid: 2\n    name: b");
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"data".to_vec()),
                Ev::Sa(2),
                Ev::So,
                Ev::Key(b"pid".to_vec()),
                Ev::Scalar("i:1".into()),
                Ev::Key(b"name".to_vec()),
                Ev::Scalar("s:a".into()),
                Ev::Eo,
                Ev::So,
                Ev::Key(b"pid".to_vec()),
                Ev::Scalar("i:2".into()),
                Ev::Key(b"name".to_vec()),
                Ev::Scalar("s:b".into()),
                Ev::Eo,
                Ev::Ea,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn parses_root_scalar_and_root_array() {
        assert_eq!(run(b"42"), vec![Ev::Scalar("i:42".into())]);
        assert_eq!(
            run(b"[3]: 1,2,3"),
            vec![
                Ev::Sa(3),
                Ev::Scalar("i:1".into()),
                Ev::Scalar("i:2".into()),
                Ev::Scalar("i:3".into()),
                Ev::Ea,
            ]
        );
    }

    #[test]
    fn quoted_strings_with_commas_stay_single_cells() {
        let events = run(b"rows[1]{a,b}:\n  \"x,y\",2");
        assert!(events.contains(&Ev::Scalar("q:x,y".into())));
    }

    #[test]
    fn wrong_row_width_faults() {
        let fault = run_err(b"rows[1]{a,b,c}:\n  1,2");
        assert_eq!(fault.code, FaultCode::WrongRowWidth);
        assert_eq!(fault.line, 2);
    }

    #[test]
    fn row_count_mismatch_faults() {
        assert_eq!(
            run_err(b"rows[2]{a}:\n  1").code,
            FaultCode::WrongArrayLength
        );
        assert_eq!(
            run_err(b"rows[1]{a}:\n  1\n  2").code,
            FaultCode::WrongArrayLength
        );
    }

    #[test]
    fn duplicate_keys_fault_in_strict() {
        assert_eq!(run_err(b"a: 1\na: 2").code, FaultCode::DuplicateKey);
    }

    #[test]
    fn unclosed_quote_names_the_line() {
        let fault = run_err(b"rows[1]{pid}:\n  \"oops");
        assert_eq!(fault.code, FaultCode::UnclosedQuote);
        assert_eq!(fault.line, 2);
    }

    #[test]
    fn empty_document_is_empty_object() {
        assert_eq!(run(b""), vec![Ev::So, Ev::Eo]);
    }
}
