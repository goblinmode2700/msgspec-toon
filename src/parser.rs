//! Structural parser: drives a `Consumer` from scanned lines.
//!
//! Grammar covered: root objects, root arrays (inline, tabular, keyed, list
//! form), root scalars, literal `[]` empty arrays, nested objects by
//! indentation, per-header delimiters, keyed tabular objects, nested field
//! groups, and list arrays with `- ` items (scalars, objects, arrays).
//!
//! Strictness: strict mode enforces declared lengths, row widths, duplicate
//! keys, blank-line prohibitions inside array bodies, and malformed-header
//! errors. Non-strict mode implements the spec-mandated leniencies: malformed
//! headers fall through to key-value lines, counts follow the actual rows,
//! and duplicate keys resolve last-write-wins.

use crate::error::{Fault, FaultCode, Position};
use crate::event::{Consumer, ScalarToken, StringToken};
use crate::header::{FieldNode, Header, HeaderOutcome, parse_header, parse_string_token};
use crate::scalar::{
    classify_bare, find_unquoted, scan_quoted, split_cells, trim_spaces, unescape,
};
use crate::scan::{Line, Lines};

pub fn parse<C: Consumer>(
    input: &[u8],
    strict: bool,
    indent_size: usize,
    consumer: &mut C,
) -> Result<(), Fault> {
    if std::str::from_utf8(input).is_err() {
        return Err(Fault::syntax(FaultCode::InvalidUtf8, 1, None));
    }

    let mut lines = Lines::new(input, strict, indent_size);
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
    if first.content == b"[]" {
        lines.advance()?;
        consumer.start_array(0, at)?;
        consumer.end_array(at)?;
        return expect_end(&mut lines);
    }

    match parse_header(first.content, strict, at)? {
        HeaderOutcome::Header(header) if header.key.is_none() => {
            lines.advance()?;
            parse_array_or_keyed_body(&mut lines, &header, 0, at, strict, consumer)?;
            expect_end(&mut lines)
        }
        HeaderOutcome::Header(_) => parse_root_object(&mut lines, strict, consumer, at),
        HeaderOutcome::Malformed(code) if strict => Err(Fault::syntax_at(code, at)),
        HeaderOutcome::Malformed(_) | HeaderOutcome::NotHeader => {
            if entry_colon(first.content).is_some() {
                parse_root_object(&mut lines, strict, consumer, at)
            } else {
                lines.advance()?;
                consumer.scalar(classify_value(first.content, at)?, at)?;
                expect_end(&mut lines)
            }
        }
    }
}

fn parse_root_object<C: Consumer>(
    lines: &mut Lines<'_>,
    strict: bool,
    consumer: &mut C,
    at: Position,
) -> Result<(), Fault> {
    consumer.start_object(at)?;
    parse_object_body(lines, 0, None, strict, consumer)?;
    consumer.end_object(at)?;
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
    match parse_header(content, strict, at)? {
        HeaderOutcome::Header(header) => {
            let key = header
                .key
                .ok_or(Fault::syntax_at(FaultCode::ExpectedKey, at))?;
            note_key(&key, at, strict, seen)?;
            consumer.key(key, at)?;
            return parse_array_or_keyed_body(lines, &header, depth, at, strict, consumer);
        }
        HeaderOutcome::Malformed(code) if strict => {
            return Err(Fault::syntax_at(code, at));
        }
        HeaderOutcome::Malformed(_) | HeaderOutcome::NotHeader => {}
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

    let value = &rest[1..];
    let value_at = Position {
        line: at.line,
        column: at.column + colon as u32 + 2,
    };
    consumer.key(key, at)?;
    if value == b"[]" {
        consumer.start_array(0, value_at)?;
        consumer.end_array(value_at)?;
        return Ok(());
    }
    consumer.scalar(classify_value(value, value_at)?, value_at)?;
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

/// Pull the next array row/item line at `depth + 1`.
///
/// Strict mode: the row must exist when `remaining > 0` (else
/// WrongArrayLength), and a blank line before any row but the first is an
/// error. Non-strict mode: rows simply stop when the indentation stops
/// matching, regardless of the declared count.
fn next_body_line<'a>(
    lines: &mut Lines<'a>,
    depth: usize,
    strict: bool,
    first_row: bool,
    remaining: usize,
) -> Result<Option<Line<'a>>, Fault> {
    match lines.peek()? {
        Some(line) if line.depth == depth + 1 => {
            if strict && line.blank_before && !first_row {
                return Err(Fault::syntax_at(FaultCode::BlankLineInArray, line.position));
            }
            lines.advance()?;
            Ok(Some(line))
        }
        Some(line) if strict && remaining > 0 => {
            Err(Fault::syntax_at(FaultCode::WrongArrayLength, line.position))
        }
        None if strict && remaining > 0 => Err(Fault::syntax(
            FaultCode::WrongArrayLength,
            lines.current_line_number(),
            None,
        )),
        _ => Ok(None),
    }
}

fn parse_array_or_keyed_body<C: Consumer>(
    lines: &mut Lines<'_>,
    header: &Header<'_>,
    depth: usize,
    at: Position,
    strict: bool,
    consumer: &mut C,
) -> Result<(), Fault> {
    if header.keyed {
        return parse_keyed_body(lines, header, depth, at, strict, consumer);
    }
    parse_array_body(lines, header, depth, at, strict, consumer)
}

/// Row-count loop shared by tabular, keyed, and list bodies: strict reads
/// exactly `declared_len` rows and rejects extras; non-strict reads whatever
/// rows are present.
fn body_rows<'a>(
    lines: &mut Lines<'a>,
    depth: usize,
    strict: bool,
    declared_len: usize,
    mut on_row: impl FnMut(&mut Lines<'a>, Line<'a>) -> Result<(), Fault>,
) -> Result<(), Fault> {
    let mut index = 0usize;
    loop {
        let remaining = declared_len.saturating_sub(index);
        if strict && remaining == 0 {
            return reject_extra_rows(lines, depth);
        }
        let Some(row) = next_body_line(lines, depth, strict, index == 0, remaining)? else {
            return Ok(());
        };
        on_row(lines, row)?;
        index += 1;
    }
}

fn reject_extra_rows(lines: &mut Lines<'_>, depth: usize) -> Result<(), Fault> {
    if let Some(line) = lines.peek()?
        && line.depth > depth
    {
        return Err(Fault::syntax_at(FaultCode::WrongArrayLength, line.position));
    }
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
        body_rows(lines, depth, strict, header.declared_len, |_, row| {
            let cells = split_cells(row.content, header.delimiter);
            if cells.len() != leaf_count {
                return Err(Fault::syntax_at(FaultCode::WrongRowWidth, row.position));
            }
            consumer.start_object(row.position)?;
            let mut cursor = 0usize;
            emit_row_fields(&header.fields, &cells, &mut cursor, row.position, consumer)?;
            consumer.end_object(row.position)
        })?;
    } else if let Some(inline) = header.inline_values {
        let cells = split_cells(inline, header.delimiter);
        if strict && cells.len() != header.declared_len {
            return Err(Fault::syntax_at(FaultCode::WrongArrayLength, at));
        }
        for cell in cells {
            consumer.scalar(classify_value(cell, at)?, at)?;
        }
    } else {
        body_rows(lines, depth, strict, header.declared_len, |lines, item| {
            parse_list_item(item.content, item.position, lines, depth, strict, consumer)
        })?;
    }

    consumer.end_array(at)?;
    Ok(())
}

/// A keyed tabular body: `key[N:]{fields}:` rows are `rowkey: cells` and the
/// construct denotes an object of field-group objects.
fn parse_keyed_body<C: Consumer>(
    lines: &mut Lines<'_>,
    header: &Header<'_>,
    depth: usize,
    at: Position,
    strict: bool,
    consumer: &mut C,
) -> Result<(), Fault> {
    let leaf_count = header.leaf_count();
    consumer.start_object(at)?;
    let mut seen: Vec<Vec<u8>> = Vec::new();
    body_rows(lines, depth, strict, header.declared_len, |_, row| {
        let Some(colon) = entry_colon(row.content) else {
            // Non-strict decoders skip an entry-depth line without a colon.
            if strict {
                return Err(Fault::syntax_at(FaultCode::ExpectedKey, row.position));
            }
            return Ok(());
        };
        let row_key = parse_string_token(trim_spaces(&row.content[..colon]), row.position)?;
        note_key(&row_key, row.position, strict, &mut seen)?;
        let rest = trim_spaces(&row.content[colon + 1..]);
        if rest.is_empty() {
            // An entry row must carry cells after its key.
            return Err(Fault::syntax_at(FaultCode::WrongRowWidth, row.position));
        }
        let cells = split_cells(rest, header.delimiter);
        if cells.len() != leaf_count {
            return Err(Fault::syntax_at(FaultCode::WrongRowWidth, row.position));
        }
        consumer.key(row_key, row.position)?;
        consumer.start_object(row.position)?;
        let mut cursor = 0usize;
        emit_row_fields(&header.fields, &cells, &mut cursor, row.position, consumer)?;
        consumer.end_object(row.position)
    })?;
    consumer.end_object(at)?;
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

    if item == b"[]" {
        consumer.start_array(0, item_at)?;
        consumer.end_array(item_at)?;
        return Ok(());
    }

    match parse_header(item, strict, item_at)? {
        HeaderOutcome::Header(header) if header.key.is_none() => {
            // An anonymous nested array item: `- [2]: 1,2` or block form.
            // A keyless fields-bearing or keyed header is not a valid item.
            if !header.fields.is_empty() || header.keyed {
                return Err(Fault::syntax_at(FaultCode::MalformedHeader, item_at));
            }
            return parse_array_body(lines, &header, depth + 1, item_at, strict, consumer);
        }
        HeaderOutcome::Header(header) => {
            // An object item whose first entry is an array; the item's fields
            // sit two levels below the list base, so the array body's rows
            // sit at depth + 3.
            consumer.start_object(item_at)?;
            let key = header.key.as_ref().expect("checked above");
            let mut seen = vec![token_owned_bytes(key)];
            consumer.key(*key, item_at)?;
            parse_array_or_keyed_body(lines, &header, depth + 2, item_at, strict, consumer)?;
            continue_object_item(lines, depth, strict, consumer, &mut seen)?;
            consumer.end_object(item_at)?;
            return Ok(());
        }
        HeaderOutcome::Malformed(code) if strict => {
            return Err(Fault::syntax_at(code, item_at));
        }
        HeaderOutcome::Malformed(_) | HeaderOutcome::NotHeader => {}
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
        if strict && line.blank_before {
            return Err(Fault::syntax_at(FaultCode::BlankLineInArray, line.position));
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
                ScalarToken::Quoted { inner, escaped } => {
                    format!(
                        "q:{}",
                        String::from_utf8(unescape(inner, escaped).into_owned()).unwrap()
                    )
                }
            };
            self.events.push(Ev::Scalar(text));
            Ok(())
        }
    }

    fn run(input: &[u8]) -> Vec<Ev> {
        let mut recorder = Recorder::default();
        parse(input, true, 2, &mut recorder).unwrap();
        recorder.events
    }

    fn run_nonstrict(input: &[u8]) -> Vec<Ev> {
        let mut recorder = Recorder::default();
        parse(input, false, 2, &mut recorder).unwrap();
        recorder.events
    }

    fn run_err(input: &[u8]) -> Fault {
        let mut recorder = Recorder::default();
        parse(input, true, 2, &mut recorder).unwrap_err()
    }

    #[test]
    fn parses_challenge_shape() {
        let events = run(
            b"workers[2]{pid,provider,metadata{alias,region}}:\n  20324,claude,worker-a,west\n  80916,claude,worker-b,east",
        );
        assert_eq!(events.len(), 31);
        assert_eq!(events[0], Ev::So);
        assert_eq!(events[1], Ev::Key(b"workers".to_vec()));
        assert_eq!(events[2], Ev::Sa(2));
        assert!(events.contains(&Ev::Scalar("i:20324".into())));
        assert!(events.contains(&Ev::Scalar("s:worker-b".into())));
    }

    #[test]
    fn parses_keyed_tabular_objects() {
        let events = run(
            b"servers[2:]{host,port}:\n  alpha: a.example.com,8080\n  beta: b.example.com,9090",
        );
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"servers".to_vec()),
                Ev::So,
                Ev::Key(b"alpha".to_vec()),
                Ev::So,
                Ev::Key(b"host".to_vec()),
                Ev::Scalar("s:a.example.com".into()),
                Ev::Key(b"port".to_vec()),
                Ev::Scalar("i:8080".into()),
                Ev::Eo,
                Ev::Key(b"beta".to_vec()),
                Ev::So,
                Ev::Key(b"host".to_vec()),
                Ev::Scalar("s:b.example.com".into()),
                Ev::Key(b"port".to_vec()),
                Ev::Scalar("i:9090".into()),
                Ev::Eo,
                Ev::Eo,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn parses_root_keyed_header() {
        let events = run(b"[2:]{age}:\n  alice: 30\n  bob: 25");
        assert_eq!(events[0], Ev::So);
        assert!(events.contains(&Ev::Key(b"alice".to_vec())));
        assert!(events.contains(&Ev::Scalar("i:25".into())));
    }

    #[test]
    fn parses_pipe_and_tab_delimiters() {
        let events = run(b"tags[3|]: reading|gaming|coding");
        assert!(events.contains(&Ev::Scalar("s:gaming".into())));
        let events = run(b"orders[2|]{id|geo{lat|lon}}:\n  1|50|10\n  2|40|-100");
        assert!(events.contains(&Ev::Scalar("i:-100".into())));
    }

    #[test]
    fn parses_empty_array_literals() {
        assert_eq!(
            run(b"items: []"),
            vec![
                Ev::So,
                Ev::Key(b"items".to_vec()),
                Ev::Sa(0),
                Ev::Ea,
                Ev::Eo
            ]
        );
        assert_eq!(run(b"[]"), vec![Ev::Sa(0), Ev::Ea]);
        assert_eq!(
            run(b"items[2]:\n  - []\n  - [1]: x"),
            vec![
                Ev::So,
                Ev::Key(b"items".to_vec()),
                Ev::Sa(2),
                Ev::Sa(0),
                Ev::Ea,
                Ev::Sa(1),
                Ev::Scalar("s:x".into()),
                Ev::Ea,
                Ev::Ea,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn parses_list_item_with_tabular_first_field() {
        let events = run(b"items[1]:\n  - users[2]{id}:\n      1\n      2\n    status: active");
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"items".to_vec()),
                Ev::Sa(1),
                Ev::So,
                Ev::Key(b"users".to_vec()),
                Ev::Sa(2),
                Ev::So,
                Ev::Key(b"id".to_vec()),
                Ev::Scalar("i:1".into()),
                Ev::Eo,
                Ev::So,
                Ev::Key(b"id".to_vec()),
                Ev::Scalar("i:2".into()),
                Ev::Eo,
                Ev::Ea,
                Ev::Key(b"status".to_vec()),
                Ev::Scalar("s:active".into()),
                Ev::Eo,
                Ev::Ea,
                Ev::Eo,
            ]
        );
    }

    #[test]
    fn nonstrict_keeps_extra_rows_and_falls_through_malformed_headers() {
        let events = run_nonstrict(b"a[1]:\n  - 1\n  - 2");
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"a".to_vec()),
                Ev::Sa(1),
                Ev::Scalar("i:1".into()),
                Ev::Scalar("i:2".into()),
                Ev::Ea,
                Ev::Eo,
            ]
        );
        let events = run_nonstrict(b"key[]: 1,2");
        assert_eq!(
            events,
            vec![
                Ev::So,
                Ev::Key(b"key[]".to_vec()),
                Ev::Scalar("s:1,2".into()),
                Ev::Eo
            ]
        );
    }

    #[test]
    fn strict_rejects_blank_lines_inside_arrays() {
        assert_eq!(
            run_err(b"items[3]:\n  - a\n\n  - b\n  - c").code,
            FaultCode::BlankLineInArray
        );
        assert_eq!(
            run_err(b"items[2]{id}:\n  1\n\n  2").code,
            FaultCode::BlankLineInArray
        );
        // ... but a blank between the header and the first row is fine.
        assert!(run(b"m[2:]{v}:\n\n  a: 1\n  b: 2").contains(&Ev::Key(b"b".to_vec())));
    }

    #[test]
    fn strict_rejects_malformed_headers() {
        assert_eq!(
            run_err(b"foo [2]: bar,baz").code,
            FaultCode::MalformedHeader
        );
        assert_eq!(run_err(b"items[03]: a,b,c").code, FaultCode::InvalidLength);
        assert_eq!(
            run_err(b"items[1]:\n  - [2]{x}:").code,
            FaultCode::MalformedHeader
        );
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
