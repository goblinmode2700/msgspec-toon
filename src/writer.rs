//! Canonical output writer: LF newlines, no trailing newline at the root.
//! Indentation width is a spec-defined option (default 2); everything else
//! about the wire stays knob-free.

pub struct Writer {
    out: Vec<u8>,
    indent_width: usize,
}

impl Writer {
    pub fn with_capacity(capacity: usize, indent_width: usize) -> Self {
        Self {
            out: Vec::with_capacity(capacity),
            indent_width,
        }
    }

    pub fn bytes(&mut self, value: &[u8]) {
        self.out.extend_from_slice(value);
    }

    pub fn byte(&mut self, value: u8) {
        self.out.push(value);
    }

    pub fn text(&mut self, value: &str) {
        self.out.extend_from_slice(value.as_bytes());
    }

    pub fn indent(&mut self, depth: usize) {
        self.out
            .resize(self.out.len() + depth * self.indent_width, b' ');
    }

    pub fn newline(&mut self) {
        self.out.push(b'\n');
    }

    pub fn finish(mut self) -> Vec<u8> {
        if self.out.last() == Some(&b'\n') {
            self.out.pop();
        }
        self.out
    }
}
