//! Scalar classification, quoted-string scanning, and unescaping.
//!
//! Classification works on borrowed bytes; nothing here touches Python.

use std::borrow::Cow;

use memchr::memchr;

use crate::error::{Fault, FaultCode, Position};
use crate::event::ScalarToken;

/// Classify an unquoted token. Quoted tokens are built by the caller, which
/// knows the quote boundaries.
///
/// One pass over the number grammar (optimization P2): integer digits, an
/// optional fraction, an optional exponent. The previous implementation ran
/// an integer scan and then re-scanned the same bytes for the float grammar,
/// so every bare string paid two failed passes. Leading zeros are not
/// canonical numbers; they classify as strings.
pub fn classify_bare(token: &[u8]) -> ScalarToken<'_> {
    match token {
        b"null" => return ScalarToken::Null,
        b"true" => return ScalarToken::Bool(true),
        b"false" => return ScalarToken::Bool(false),
        _ => {}
    }
    let body = token.strip_prefix(b"-").unwrap_or(token);
    let mut index = 0;
    while index < body.len() && body[index].is_ascii_digit() {
        index += 1;
    }
    let integer_digits = index;
    if integer_digits == 0 || (integer_digits > 1 && body[0] == b'0') {
        return ScalarToken::BareString(token);
    }
    if index == body.len() {
        return ScalarToken::Integer(token);
    }
    let mut fraction = false;
    if body[index] == b'.' {
        index += 1;
        let first_fraction_digit = index;
        while index < body.len() && body[index].is_ascii_digit() {
            index += 1;
        }
        if index == first_fraction_digit {
            return ScalarToken::BareString(token);
        }
        fraction = true;
    }
    let mut exponent = false;
    if index < body.len() && matches!(body[index], b'e' | b'E') {
        index += 1;
        if index < body.len() && matches!(body[index], b'+' | b'-') {
            index += 1;
        }
        let first_exponent_digit = index;
        while index < body.len() && body[index].is_ascii_digit() {
            index += 1;
        }
        if index == first_exponent_digit {
            return ScalarToken::BareString(token);
        }
        exponent = true;
    }
    if index != body.len() || !(fraction || exponent) {
        return ScalarToken::BareString(token);
    }
    ScalarToken::Float(token)
}

/// Scan a quoted string starting at `content[start] == b'"'`. Returns the
/// index one past the closing quote and whether escapes occur. Escape
/// sequences are validated here so later unescaping cannot fail.
pub fn scan_quoted(content: &[u8], start: usize, at: Position) -> Result<(usize, bool), Fault> {
    debug_assert_eq!(content[start], b'"');
    let mut index = start + 1;
    let mut escaped = false;
    while index < content.len() {
        match content[index] {
            b'"' => return Ok((index + 1, escaped)),
            b'\\' => {
                escaped = true;
                let escape_column = at.column + index as u32;
                index += 1;
                let invalid =
                    || Fault::syntax(FaultCode::InvalidEscape, at.line, Some(escape_column));
                match content.get(index) {
                    Some(b'"' | b'\\' | b'/' | b'b' | b'f' | b'n' | b'r' | b't') => index += 1,
                    Some(b'u') => {
                        let hex = content.get(index + 1..index + 5).ok_or_else(invalid)?;
                        if !hex.iter().all(u8::is_ascii_hexdigit) {
                            return Err(invalid());
                        }
                        let code = u32::from_str_radix(
                            std::str::from_utf8(hex).expect("hex digits are ASCII"),
                            16,
                        )
                        .expect("validated hex");
                        index += 5;
                        if (0xD800..0xDC00).contains(&code) {
                            // A high surrogate must pair with an immediately
                            // following low surrogate escape.
                            if content.get(index) != Some(&b'\\')
                                || content.get(index + 1) != Some(&b'u')
                            {
                                return Err(invalid());
                            }
                            let low_hex = content.get(index + 2..index + 6).ok_or_else(invalid)?;
                            if !low_hex.iter().all(u8::is_ascii_hexdigit) {
                                return Err(invalid());
                            }
                            let low = u32::from_str_radix(
                                std::str::from_utf8(low_hex).expect("hex digits are ASCII"),
                                16,
                            )
                            .expect("validated hex");
                            if !(0xDC00..0xE000).contains(&low) {
                                return Err(invalid());
                            }
                            index += 6;
                        } else if (0xDC00..0xE000).contains(&code) {
                            // A lone low surrogate is never valid.
                            return Err(invalid());
                        }
                    }
                    _ => return Err(invalid()),
                }
            }
            _ => index += 1,
        }
    }
    Err(Fault::syntax(
        FaultCode::UnclosedQuote,
        at.line,
        Some(at.column + start as u32),
    ))
}

/// Unescape the inner bytes of a validated quoted string.
pub fn unescape(inner: &[u8], escaped: bool) -> Cow<'_, [u8]> {
    if !escaped {
        return Cow::Borrowed(inner);
    }
    let mut out = Vec::with_capacity(inner.len());
    let mut index = 0;
    while index < inner.len() {
        if inner[index] == b'\\' {
            index += 1;
            match inner[index] {
                b'"' => out.push(b'"'),
                b'\\' => out.push(b'\\'),
                b'/' => out.push(b'/'),
                b'b' => out.push(0x08),
                b'f' => out.push(0x0C),
                b'n' => out.push(b'\n'),
                b'r' => out.push(b'\r'),
                b't' => out.push(b'\t'),
                b'u' => {
                    let hex = std::str::from_utf8(&inner[index + 1..index + 5]).unwrap();
                    let mut code = u32::from_str_radix(hex, 16).unwrap();
                    index += 4;
                    // Combine a UTF-16 surrogate pair when present.
                    if (0xD800..0xDC00).contains(&code)
                        && inner.get(index + 1..index + 3) == Some(b"\\u")
                    {
                        let low_hex =
                            std::str::from_utf8(&inner[index + 3..index + 7]).unwrap_or("");
                        if let Ok(low) = u32::from_str_radix(low_hex, 16)
                            && (0xDC00..0xE000).contains(&low)
                        {
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                            index += 6;
                        }
                    }
                    let ch = char::from_u32(code).unwrap_or(char::REPLACEMENT_CHARACTER);
                    let mut buf = [0u8; 4];
                    out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                }
                _ => unreachable!("escapes validated by scan_quoted"),
            }
            index += 1;
        } else {
            out.push(inner[index]);
            index += 1;
        }
    }
    Cow::Owned(out)
}

/// Find the first occurrence of `needle` outside quoted spans.
/// The first structural mark on a line: the first unquoted `[` (a possible
/// header) or the first unquoted `:` (a possible entry separator), whichever
/// comes first (optimization P3). The first mark decides the line class on
/// its own — a colon before any bracket is never a header, a bracket before
/// any colon starts one — so the scan stops there instead of walking the
/// whole line, and the dominant `key: value` line class stops at its colon.
/// The other mark is reported `None` and, where a fall-through path still
/// needs the colon after a bracket, `resolved_colon` completes the scan from
/// the bracket. The quote-state machine is `find_unquoted`'s own.
pub struct LineMarks {
    pub bracket: Option<usize>,
    pub colon: Option<usize>,
}

pub fn scan_line_marks(content: &[u8]) -> LineMarks {
    let mut in_quote = false;
    let mut index = 0;
    while index < content.len() {
        let byte = content[index];
        if in_quote {
            if byte == b'\\' {
                index += 1;
            } else if byte == b'"' {
                in_quote = false;
            }
        } else if byte == b'"' {
            in_quote = true;
        } else if byte == b'[' {
            return LineMarks {
                bracket: Some(index),
                colon: None,
            };
        } else if byte == b':' {
            return LineMarks {
                bracket: None,
                colon: Some(index),
            };
        }
        index += 1;
    }
    LineMarks {
        bracket: None,
        colon: None,
    }
}

/// The line's first unquoted colon, given its marks: either the scan stopped
/// at it, or it stopped at an earlier bracket and the colon (if any) lies
/// beyond — the bracket position is outside any quote, so the completion
/// scan starts there with a clean quote state.
pub fn resolved_colon(content: &[u8], marks: &LineMarks) -> Option<usize> {
    marks
        .colon
        .or_else(|| find_unquoted(content, b':', marks.bracket?))
}

pub fn find_unquoted(content: &[u8], needle: u8, from: usize) -> Option<usize> {
    let mut index = from;
    let mut in_quote = false;
    while index < content.len() {
        let byte = content[index];
        if in_quote {
            if byte == b'\\' {
                index += 1;
            } else if byte == b'"' {
                in_quote = false;
            }
        } else if byte == b'"' {
            in_quote = true;
        } else if byte == needle {
            return Some(index);
        }
        index += 1;
    }
    None
}

/// Split a row into cells on an unquoted delimiter.
pub fn split_cells(content: &[u8], delimiter: u8) -> Vec<&[u8]> {
    let mut cells = Vec::new();
    split_cells_into(content, delimiter, &mut cells);
    cells
}

/// Split into a caller-owned buffer so tabular rows reuse one allocation
/// (optimization D2). Quote-free rows — the overwhelming majority — take a
/// plain `memchr` scan instead of byte-at-a-time quote tracking (P1).
pub fn split_cells_into<'a>(content: &'a [u8], delimiter: u8, cells: &mut Vec<&'a [u8]>) {
    cells.clear();
    if memchr(b'"', content).is_none() {
        let mut start = 0;
        for end in memchr::memchr_iter(delimiter, content) {
            cells.push(trim_spaces(&content[start..end]));
            start = end + 1;
        }
        cells.push(trim_spaces(&content[start..]));
        return;
    }
    let mut start = 0;
    loop {
        match find_unquoted(content, delimiter, start) {
            Some(end) => {
                cells.push(trim_spaces(&content[start..end]));
                start = end + 1;
            }
            None => {
                cells.push(trim_spaces(&content[start..]));
                return;
            }
        }
    }
}

pub fn trim_spaces(mut bytes: &[u8]) -> &[u8] {
    while let Some((b' ', rest)) = bytes.split_first() {
        bytes = rest;
    }
    while let Some((b' ', rest)) = bytes.split_last() {
        bytes = rest;
    }
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_scalars() {
        assert!(matches!(classify_bare(b"null"), ScalarToken::Null));
        assert!(matches!(classify_bare(b"true"), ScalarToken::Bool(true)));
        assert!(matches!(classify_bare(b"42"), ScalarToken::Integer(_)));
        assert!(matches!(classify_bare(b"-7"), ScalarToken::Integer(_)));
        assert!(matches!(
            classify_bare(b"9007199254740993"),
            ScalarToken::Integer(_)
        ));
        assert!(matches!(classify_bare(b"1.5"), ScalarToken::Float(_)));
        assert!(matches!(classify_bare(b"1e-7"), ScalarToken::Float(_)));
        assert!(matches!(classify_bare(b"05"), ScalarToken::BareString(_)));
        assert!(matches!(
            classify_bare(b"worker-a"),
            ScalarToken::BareString(_)
        ));
        assert!(matches!(
            classify_bare(b"1.2.3"),
            ScalarToken::BareString(_)
        ));
    }

    #[test]
    fn scans_and_unescapes_quotes() {
        let at = Position { line: 1, column: 1 };
        let content = br#""a\nb" rest"#;
        let (end, escaped) = scan_quoted(content, 0, at).unwrap();
        assert_eq!(end, 6);
        assert!(escaped);
        assert_eq!(unescape(&content[1..end - 1], escaped).as_ref(), b"a\nb");
    }

    #[test]
    fn splits_cells_respecting_quotes() {
        let cells = split_cells(br#"1,"a,b",2"#, b',');
        assert_eq!(cells, vec![&b"1"[..], &br#""a,b""#[..], &b"2"[..]]);
    }

    #[test]
    fn unclosed_quote_is_a_fault() {
        let at = Position { line: 3, column: 1 };
        let fault = scan_quoted(br#""abc"#, 0, at).unwrap_err();
        assert_eq!(fault.code, FaultCode::UnclosedQuote);
        assert_eq!(fault.line, 3);
    }
}

#[cfg(test)]
mod p2_differential {
    use super::*;
    use crate::event::ScalarToken;

    /// The implementation P2 replaced, kept here only as the differential
    /// oracle: an integer scan followed by an independent float scan.
    fn classify_bare_two_pass(token: &[u8]) -> ScalarToken<'_> {
        fn is_integer_literal(token: &[u8]) -> bool {
            let digits = token.strip_prefix(b"-").unwrap_or(token);
            if digits.is_empty() || !digits.iter().all(u8::is_ascii_digit) {
                return false;
            }
            digits.len() == 1 || digits[0] != b'0'
        }
        fn is_float_literal(token: &[u8]) -> bool {
            let body = token.strip_prefix(b"-").unwrap_or(token);
            if body.is_empty() {
                return false;
            }
            let (mantissa, exponent) = match body.iter().position(|&b| b == b'e' || b == b'E') {
                Some(index) => (&body[..index], Some(&body[index + 1..])),
                None => (body, None),
            };
            let (int_part, frac_part) = match mantissa.iter().position(|&b| b == b'.') {
                Some(index) => (&mantissa[..index], Some(&mantissa[index + 1..])),
                None => (mantissa, None),
            };
            if int_part.is_empty() || !int_part.iter().all(u8::is_ascii_digit) {
                return false;
            }
            if int_part.len() > 1 && int_part[0] == b'0' {
                return false;
            }
            if let Some(frac) = frac_part
                && (frac.is_empty() || !frac.iter().all(u8::is_ascii_digit))
            {
                return false;
            }
            match exponent {
                Some(exp) => {
                    let exp = exp
                        .strip_prefix(b"+")
                        .or_else(|| exp.strip_prefix(b"-"))
                        .unwrap_or(exp);
                    !exp.is_empty() && exp.iter().all(u8::is_ascii_digit)
                }
                None => frac_part.is_some(),
            }
        }
        match token {
            b"null" => ScalarToken::Null,
            b"true" => ScalarToken::Bool(true),
            b"false" => ScalarToken::Bool(false),
            _ if is_integer_literal(token) => ScalarToken::Integer(token),
            _ if is_float_literal(token) => ScalarToken::Float(token),
            _ => ScalarToken::BareString(token),
        }
    }

    fn same(token: &[u8]) -> bool {
        matches!(
            (classify_bare(token), classify_bare_two_pass(token)),
            (ScalarToken::Null, ScalarToken::Null)
                | (ScalarToken::Bool(true), ScalarToken::Bool(true))
                | (ScalarToken::Bool(false), ScalarToken::Bool(false))
                | (ScalarToken::Integer(_), ScalarToken::Integer(_))
                | (ScalarToken::Float(_), ScalarToken::Float(_))
                | (ScalarToken::BareString(_), ScalarToken::BareString(_))
        )
    }

    /// Exhaustive over the alphabet that decides the number grammar. Every
    /// token up to length 5 is checked against the old implementation.
    #[test]
    fn one_pass_classifier_matches_the_two_pass_one() {
        const ALPHABET: &[u8] = b"0192.eE+-n";
        let mut checked = 0usize;
        let mut token = Vec::new();
        for length in 0..=5usize {
            let mut indices = vec![0usize; length];
            loop {
                token.clear();
                token.extend(indices.iter().map(|&i| ALPHABET[i]));
                assert!(
                    same(&token),
                    "divergence on {:?}",
                    String::from_utf8_lossy(&token)
                );
                checked += 1;
                let mut position = length;
                loop {
                    if position == 0 {
                        break;
                    }
                    position -= 1;
                    indices[position] += 1;
                    if indices[position] < ALPHABET.len() {
                        break;
                    }
                    indices[position] = 0;
                    if position == 0 {
                        break;
                    }
                }
                if length == 0 || indices.iter().all(|&i| i == 0) {
                    break;
                }
            }
        }
        for literal in [
            &b"null"[..],
            b"true",
            b"false",
            b"nan",
            b"inf",
            b"-inf",
            b"NaN",
            b"1e309",
            b"-0",
            b"0.0",
            b"00",
            b"01",
            b"1_000",
            b"1.2.3",
            b"--1",
        ] {
            assert!(
                same(literal),
                "divergence on {:?}",
                String::from_utf8_lossy(literal)
            );
            checked += 1;
        }
        assert!(checked > 100_000, "differential was too small: {checked}");
        println!("P2 differential: {checked} tokens, zero divergences");
    }
}

#[cfg(test)]
mod p3_differential {
    use super::*;

    /// The reference the fused scanner must agree with: two independent
    /// quote-aware searches, exactly what the implementation P3 replaced did.
    fn naive_marks(content: &[u8]) -> (Option<usize>, Option<usize>) {
        (
            find_unquoted(content, b'[', 0),
            find_unquoted(content, b':', 0),
        )
    }

    /// `scan_line_marks` stops at whichever structural mark comes first and
    /// reports only that one, on the claim that the first unquoted mark
    /// decides the line class by itself. That claim is what this checks: the
    /// mark it reports must be the earlier of the two the naive scan finds,
    /// and `resolved_colon` must recover the true colon in every case.
    #[test]
    fn fused_scan_agrees_with_two_independent_scans() {
        const ALPHABET: &[u8] = b"a\"\\[]: -";
        let mut checked = 0usize;
        let mut content = Vec::new();
        for length in 0..=5usize {
            let mut indices = vec![0usize; length];
            loop {
                content.clear();
                content.extend(indices.iter().map(|&i| ALPHABET[i]));
                let marks = scan_line_marks(&content);
                let (bracket, colon) = naive_marks(&content);

                match (bracket, colon) {
                    (Some(b), Some(c)) if b < c => {
                        assert_eq!(marks.bracket, Some(b), "bracket-first {content:?}");
                        assert_eq!(marks.colon, None, "must not report the later colon");
                    }
                    (Some(b), Some(c)) => {
                        assert!(c < b, "equal positions are impossible");
                        assert_eq!(marks.colon, Some(c), "colon-first {content:?}");
                        assert_eq!(marks.bracket, None, "must not report the later bracket");
                    }
                    (Some(b), None) => assert_eq!(marks.bracket, Some(b), "{content:?}"),
                    (None, Some(c)) => assert_eq!(marks.colon, Some(c), "{content:?}"),
                    (None, None) => {
                        assert_eq!(marks.bracket, None, "{content:?}");
                        assert_eq!(marks.colon, None, "{content:?}");
                    }
                }

                // The fall-through path must recover the colon the fused scan
                // deliberately skipped past.
                assert_eq!(
                    resolved_colon(&content, &marks),
                    colon,
                    "resolved_colon lost the colon on {content:?}"
                );

                checked += 1;
                let mut position = length;
                loop {
                    if position == 0 {
                        break;
                    }
                    position -= 1;
                    indices[position] += 1;
                    if indices[position] < ALPHABET.len() {
                        break;
                    }
                    indices[position] = 0;
                    if position == 0 {
                        break;
                    }
                }
                if length == 0 || indices.iter().all(|&i| i == 0) {
                    break;
                }
            }
        }
        for line in [
            &br#""a:b"[2]{x}:"#[..],
            br#""a[b": x"#,
            br#"key[2]: a,b"#,
            br#"key: []"#,
            br#"- key: value"#,
            br#"- [2]: 1,2"#,
            br#"key: "quoted: colon""#,
            br#""\"":"#,
        ] {
            let marks = scan_line_marks(line);
            let (bracket, colon) = naive_marks(line);
            assert_eq!(resolved_colon(line, &marks), colon, "{line:?}");
            if let (Some(b), Some(c)) = (bracket, colon) {
                if b < c {
                    assert_eq!(marks.bracket, Some(b), "{line:?}");
                } else {
                    assert_eq!(marks.colon, Some(c), "{line:?}");
                }
            }
            checked += 1;
        }
        assert!(checked > 30_000, "differential was too small: {checked}");
        println!("P3 differential: {checked} lines, zero divergences");
    }
}
