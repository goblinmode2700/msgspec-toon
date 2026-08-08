//! Zero-copy incremental line scanner.
//!
//! Borrows slices of the input buffer; never builds a second copy of the
//! document. Skips blank lines and whole-line `#` comments (recording that a
//! blank was skipped — strict array bodies must reject blank lines), strips
//! a UTF-8 BOM on the first line and a trailing `\r` per line, and converts
//! leading spaces into a depth in indent units.

use memchr::memchr;

use crate::error::{Fault, FaultCode, Position};
use crate::limits::MAX_NESTING_DEPTH;

pub const INDENT_SIZE: usize = 2;

#[derive(Debug, Clone, Copy)]
pub struct Line<'a> {
    pub content: &'a [u8],
    pub depth: usize,
    pub position: Position,
    /// One or more blank (or whitespace-only) lines were skipped between the
    /// previous content line and this one. Comment lines do not set this.
    pub blank_before: bool,
}

pub struct Scanner<'a> {
    input: &'a [u8],
    offset: usize,
    line: u32,
    strict: bool,
    indent_size: usize,
}

impl<'a> Scanner<'a> {
    pub fn new(input: &'a [u8], strict: bool, indent_size: usize) -> Self {
        Self {
            input,
            offset: 0,
            line: 0,
            strict,
            indent_size,
        }
    }

    pub fn next_line(&mut self) -> Result<Option<Line<'a>>, Fault> {
        let mut blank_before = false;
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

            // Blank and whitespace-only lines are skipped before any
            // indentation validation: a line with no content has no depth.
            if raw.iter().all(|&byte| byte == b' ' || byte == b'\t') {
                blank_before = true;
                continue;
            }

            let mut indent = 0usize;
            while indent < raw.len() && raw[indent] == b' ' {
                indent += 1;
            }

            if raw[indent] == b'\t' {
                if self.strict {
                    return Err(Fault::syntax(
                        FaultCode::TabIndent,
                        self.line,
                        Some((indent + 1) as u32),
                    ));
                }
                // Non-strict leniency: a tab counts as one indent level.
                let mut levels = indent / self.indent_size;
                let mut cursor = indent;
                while cursor < raw.len() && (raw[cursor] == b'\t' || raw[cursor] == b' ') {
                    levels += usize::from(raw[cursor] == b'\t');
                    cursor += 1;
                }
                indent = cursor;
                // Rewrite the effective depth below via `tab_levels`.
                let mut end = raw.len();
                while end > indent && raw[end - 1] == b' ' {
                    end -= 1;
                }
                let content = &raw[indent..end];
                if content.is_empty() {
                    blank_before = true;
                    continue;
                }
                if levels > MAX_NESTING_DEPTH {
                    return Err(Fault::syntax(FaultCode::DepthLimit, self.line, Some(1)));
                }
                return Ok(Some(Line {
                    content,
                    depth: levels,
                    position: Position {
                        line: self.line,
                        column: (indent + 1) as u32,
                    },
                    blank_before,
                }));
            }

            let mut end = raw.len();
            while end > indent && raw[end - 1] == b' ' {
                end -= 1;
            }
            let content = &raw[indent..end];

            // Whole-line comments require space-only indentation; a line
            // whose indentation held a tab is handled above (non-strict) and
            // is data, not a comment. Comments are stripped before indent
            // validation — a comment has no depth of its own.
            if content.starts_with(b"#") {
                continue;
            }

            if self.strict && !indent.is_multiple_of(self.indent_size) {
                return Err(Fault::syntax(FaultCode::InvalidIndent, self.line, Some(1)));
            }

            if indent / self.indent_size > MAX_NESTING_DEPTH {
                return Err(Fault::syntax(FaultCode::DepthLimit, self.line, Some(1)));
            }

            return Ok(Some(Line {
                content,
                depth: indent / self.indent_size,
                position: Position {
                    line: self.line,
                    column: (indent + 1) as u32,
                },
                blank_before,
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
    pub fn new(input: &'a [u8], strict: bool, indent_size: usize) -> Self {
        Self {
            scanner: Scanner::new(input, strict, indent_size),
            peeked: None,
        }
    }

    pub fn peek(&mut self) -> Result<Option<Line<'a>>, Fault> {
        if self.peeked.is_none() {
            self.peeked = Some(self.scanner.next_line()?);
        }
        Ok(self.peeked.unwrap())
    }

    pub fn advance(&mut self) -> Result<Option<Line<'a>>, Fault> {
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
        let mut scanner = Scanner::new(b"a: 1\n  b: 2\n\n# comment\n  c: 3", true, 2);
        let first = scanner.next_line().unwrap().unwrap();
        assert_eq!(first.content, b"a: 1");
        assert_eq!(first.depth, 0);
        assert!(!first.blank_before);
        let second = scanner.next_line().unwrap().unwrap();
        assert_eq!(second.content, b"b: 2");
        assert_eq!(second.depth, 1);
        let third = scanner.next_line().unwrap().unwrap();
        assert_eq!(third.content, b"c: 3");
        assert_eq!(third.position.line, 5);
        assert!(third.blank_before);
        assert!(scanner.next_line().unwrap().is_none());
    }

    #[test]
    fn strict_rejects_tab_indent() {
        let mut scanner = Scanner::new(b"a:\n\tb: 2", true, 2);
        scanner.next_line().unwrap();
        let fault = scanner.next_line().unwrap_err();
        assert_eq!(fault.code, FaultCode::TabIndent);
        assert_eq!(fault.line, 2);
    }

    #[test]
    fn strict_rejects_odd_indent() {
        let mut scanner = Scanner::new(b"a:\n   b: 2", true, 2);
        scanner.next_line().unwrap();
        let fault = scanner.next_line().unwrap_err();
        assert_eq!(fault.code, FaultCode::InvalidIndent);
    }

    #[test]
    fn whitespace_only_line_is_blank_even_at_odd_indent() {
        let mut scanner = Scanner::new(b"a: 1\n   \nb: 2", true, 2);
        scanner.next_line().unwrap();
        let next = scanner.next_line().unwrap().unwrap();
        assert_eq!(next.content, b"b: 2");
        assert!(next.blank_before);
    }

    #[test]
    fn strips_bom_and_carriage_returns() {
        let mut scanner = Scanner::new(b"\xEF\xBB\xBFa: 1\r\nb: 2\r", true, 2);
        assert_eq!(scanner.next_line().unwrap().unwrap().content, b"a: 1");
        assert_eq!(scanner.next_line().unwrap().unwrap().content, b"b: 2");
    }

    #[test]
    fn non_strict_tab_indent_counts_as_level() {
        let mut scanner = Scanner::new(b"a:\n\t#x", false, 2);
        scanner.next_line().unwrap();
        let line = scanner.next_line().unwrap().unwrap();
        assert_eq!(line.content, b"#x");
        assert_eq!(line.depth, 1);
    }
}
