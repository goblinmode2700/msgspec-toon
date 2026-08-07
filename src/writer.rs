//! Canonical output writer. No wire knobs (canvas AD-005): two-space
//! indentation, LF newlines, no trailing newline at the root.

pub struct Writer {
    out: Vec<u8>,
}

impl Writer {
    pub fn with_capacity(capacity: usize) -> Self {
        Self { out: Vec::with_capacity(capacity) }
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
        self.out.resize(self.out.len() + depth * 2, b' ');
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
