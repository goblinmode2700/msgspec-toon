//! Zero-copy incremental line scanner.
//!
//! Borrows slices of the input buffer; never builds a second copy of the
//! document. Skips blank lines and whole-line `#` comments, strips a UTF-8
//! BOM on the first line and a trailing `\r` per line, and converts leading
//! spaces into a depth in indent units.

use memchr::memchr;

use crate::error::{Fault, FaultCode, Position};

pub const INDENT_SIZE: usize = 2;

/// The recursion in the parser is bounded by line depth; cap it so a
/// pathological document cannot overflow the native stack.
pub const MAX_DEPTH: usize = 256;

#[derive(Debug, Clone, Copy)]
pub struct Line<'a> {
    pub content: &'a [u8],
    pub depth: usize,
    pub position: Position,
}

pub struct Scanner<'a> {
    input: &'a [u8],
    offset: usize,
    line: u32,
    strict: bool,
}

impl<'a> Scanner<'a> {
    pub fn new(input: &'a [u8], strict: bool) -> Self {
        Self { input, offset: 0, line: 0, strict }
    }

    pub fn next_line(&mut self) -> Result<Option<Line<'a>>, Fault> {
        loop {
            if self.offset >= self.input.len() {
                return Ok(None);
            }

            let tail = &self.input[self.offset..];
            let width = memchr(b'\n', tail).unwrap_or(tail.len());
            let mut raw = &tail[..width];
            self.offset += width + usize::from(width < tail.len());
            self.line += 1;

            if self.line == 1 && raw.starts_with(b"\xEF\xBB\xBF") {
                raw = &raw[3..];
            }
            if raw.ends_with(b"\r") {
                raw = &raw[..raw.len() - 1];
            }

            let mut indent = 0usize;
            while indent < raw.len() && raw[indent] == b' ' {
                indent += 1;
            }

            if indent < raw.len() && raw[indent] == b'\t' {
                if self.strict {
                    return Err(Fault::syntax(
                        FaultCode::TabIndent,
                        self.line,
                        Some((indent + 1) as u32),
                    ));
                }
                while indent < raw.len() && (raw[indent] == b'\t' || raw[indent] == b' ') {
                    indent += 1;
                }
            }
            if self.strict && !indent.is_multiple_of(INDENT_SIZE) {
                return Err(Fault::syntax(FaultCode::InvalidIndent, self.line, Some(1)));
            }

            let mut end = raw.len();
            while end > indent && raw[end - 1] == b' ' {
                end -= 1;
            }
            let content = &raw[indent..end];

            if content.is_empty() || content.starts_with(b"#") {
                continue;
            }

            if indent / INDENT_SIZE > MAX_DEPTH {
                return Err(Fault::syntax(FaultCode::DepthLimit, self.line, Some(1)));
            }

            return Ok(Some(Line {
                content,
                depth: indent / INDENT_SIZE,
                position: Position { line: self.line, column: (indent + 1) as u32 },
            }));
        }
    }
}

/// A one-line lookahead over the scanner, the shape the recursive parser needs.
pub struct Lines<'a> {
    scanner: Scanner<'a>,
    peeked: Option<Option<Line<'a>>>,
}

impl<'a> Lines<'a> {
    pub fn new(input: &'a [u8], strict: bool) -> Self {
        Self { scanner: Scanner::new(input, strict), peeked: None }
    }

    pub fn peek(&mut self) -> Result<Option<Line<'a>>, Fault> {
        if self.peeked.is_none() {
            self.peeked = Some(self.scanner.next_line()?);
        }
        Ok(self.peeked.unwrap())
    }

    pub fn next(&mut self) -> Result<Option<Line<'a>>, Fault> {
        match self.peeked.take() {
            Some(line) => Ok(line),
            None => self.scanner.next_line(),
        }
    }

    pub fn current_line_number(&self) -> u32 {
        self.scanner.line
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scans_lines_with_depth() {
        let mut scanner = Scanner::new(b"a: 1\n  b: 2\n\n# comment\n  c: 3", true);
        let first = scanner.next_line().unwrap().unwrap();
        assert_eq!(first.content, b"a: 1");
        assert_eq!(first.depth, 0);
        let second = scanner.next_line().unwrap().unwrap();
        assert_eq!(second.content, b"b: 2");
        assert_eq!(second.depth, 1);
        let third = scanner.next_line().unwrap().unwrap();
        assert_eq!(third.content, b"c: 3");
        assert_eq!(third.position.line, 5);
        assert!(scanner.next_line().unwrap().is_none());
    }

    #[test]
    fn strict_rejects_tab_indent() {
        let mut scanner = Scanner::new(b"a:\n\tb: 2", true);
        scanner.next_line().unwrap();
        let fault = scanner.next_line().unwrap_err();
        assert_eq!(fault.code, FaultCode::TabIndent);
        assert_eq!(fault.line, 2);
    }

    #[test]
    fn strict_rejects_odd_indent() {
        let mut scanner = Scanner::new(b"a:\n   b: 2", true);
        scanner.next_line().unwrap();
        let fault = scanner.next_line().unwrap_err();
        assert_eq!(fault.code, FaultCode::InvalidIndent);
    }

    #[test]
    fn strips_bom_and_carriage_returns() {
        let mut scanner = Scanner::new(b"\xEF\xBB\xBFa: 1\r\nb: 2\r", true);
        assert_eq!(scanner.next_line().unwrap().unwrap().content, b"a: 1");
        assert_eq!(scanner.next_line().unwrap().unwrap().content, b"b: 2");
    }
}
