//! Scalar classification, quoted-string scanning, and unescaping.
//!
//! Classification works on borrowed bytes; nothing here touches Python.

use std::borrow::Cow;

use crate::error::{Fault, FaultCode, Position};
use crate::event::ScalarToken;

pub fn is_integer_literal(token: &[u8]) -> bool {
    let digits = token.strip_prefix(b"-").unwrap_or(token);
    if digits.is_empty() || !digits.iter().all(u8::is_ascii_digit) {
        return false;
    }
    // Leading zeros are not canonical numbers; they classify as strings.
    digits.len() == 1 || digits[0] != b'0'
}

pub fn is_float_literal(token: &[u8]) -> bool {
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

/// Classify an unquoted token. Quoted tokens are built by the caller, which
/// knows the quote boundaries.
pub fn classify_bare(token: &[u8]) -> ScalarToken<'_> {
    match token {
        b"null" => ScalarToken::Null,
        b"true" => ScalarToken::Bool(true),
        b"false" => ScalarToken::Bool(false),
        _ if is_integer_literal(token) => ScalarToken::Integer(token),
        _ if is_float_literal(token) => ScalarToken::Float(token),
        _ => ScalarToken::BareString(token),
    }
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
    let mut start = 0;
    loop {
        match find_unquoted(content, delimiter, start) {
            Some(end) => {
                cells.push(trim_spaces(&content[start..end]));
                start = end + 1;
            }
            None => {
                cells.push(trim_spaces(&content[start..]));
                return cells;
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
