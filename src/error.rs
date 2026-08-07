//! Payload-safe fault model (canvas AD-007).
//!
//! A `Fault` carries machine coordinates only. No variant stores a source
//! line, token spelling, key, cell, or value; user-facing text is formatted
//! from static templates plus coordinates.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FaultCode {
    InvalidUtf8,
    TabIndent,
    InvalidIndent,
    DepthJump,
    UnclosedQuote,
    InvalidEscape,
    UnclosedBracket,
    InvalidLength,
    UnclosedFieldGroup,
    EmptyField,
    DuplicateField,
    ContentAfterFieldsHeader,
    ContentAfterFieldGroup,
    WrongRowWidth,
    WrongArrayLength,
    MissingListItem,
    DuplicateKey,
    UnknownField,
    MissingField,
    TypeMismatch,
    TrailingContent,
    UnsupportedType,
    ExpectedKey,
    InvalidRoot,
    DepthLimit,
    Internal,
}

impl FaultCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::InvalidUtf8 => "invalid_utf8",
            Self::TabIndent => "tab_indent",
            Self::InvalidIndent => "invalid_indent",
            Self::DepthJump => "depth_jump",
            Self::UnclosedQuote => "unclosed_quote",
            Self::InvalidEscape => "invalid_escape",
            Self::UnclosedBracket => "unclosed_bracket",
            Self::InvalidLength => "invalid_length",
            Self::UnclosedFieldGroup => "unclosed_field_group",
            Self::EmptyField => "empty_field",
            Self::DuplicateField => "duplicate_field",
            Self::ContentAfterFieldsHeader => "content_after_fields_header",
            Self::ContentAfterFieldGroup => "content_after_field_group",
            Self::WrongRowWidth => "wrong_row_width",
            Self::WrongArrayLength => "wrong_array_length",
            Self::MissingListItem => "missing_list_item",
            Self::DuplicateKey => "duplicate_key",
            Self::UnknownField => "unknown_field",
            Self::MissingField => "missing_field",
            Self::TypeMismatch => "type_mismatch",
            Self::TrailingContent => "trailing_content",
            Self::UnsupportedType => "unsupported_type",
            Self::ExpectedKey => "expected_key",
            Self::InvalidRoot => "invalid_root",
            Self::DepthLimit => "depth_limit",
            Self::Internal => "internal",
        }
    }

    pub fn summary(self) -> &'static str {
        match self {
            Self::InvalidUtf8 => "input is not valid UTF-8",
            Self::TabIndent => "tab character in indentation",
            Self::InvalidIndent => "indentation is not a multiple of the indent size",
            Self::DepthJump => "indentation increased by more than one level",
            Self::UnclosedQuote => "unclosed quoted string",
            Self::InvalidEscape => "invalid escape sequence",
            Self::UnclosedBracket => "unclosed length bracket",
            Self::InvalidLength => "invalid array length",
            Self::UnclosedFieldGroup => "unclosed field group",
            Self::EmptyField => "empty field name in header",
            Self::DuplicateField => "duplicate field name in header",
            Self::ContentAfterFieldsHeader => "content after a fields header",
            Self::ContentAfterFieldGroup => "content after a field group",
            Self::WrongRowWidth => "row width does not match the header",
            Self::WrongArrayLength => "array length does not match the declaration",
            Self::MissingListItem => "expected a list item",
            Self::DuplicateKey => "duplicate object key",
            Self::UnknownField => "unknown field for the target type",
            Self::MissingField => "missing required field",
            Self::TypeMismatch => "value does not match the target type",
            Self::TrailingContent => "trailing content after the document",
            Self::UnsupportedType => "unsupported type",
            Self::ExpectedKey => "expected a key",
            Self::InvalidRoot => "invalid document root",
            Self::DepthLimit => "nesting depth limit exceeded",
            Self::Internal => "internal error",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Position {
    pub line: u32,
    pub column: u32,
}

#[derive(Debug)]
pub struct Fault {
    pub code: FaultCode,
    pub line: u32,
    pub column: Option<u32>,
    pub validation: bool,
}

impl Fault {
    pub fn syntax(code: FaultCode, line: u32, column: Option<u32>) -> Self {
        Self {
            code,
            line,
            column,
            validation: false,
        }
    }

    pub fn syntax_at(code: FaultCode, at: Position) -> Self {
        Self {
            code,
            line: at.line,
            column: Some(at.column),
            validation: false,
        }
    }

    pub fn validation_at(code: FaultCode, at: Position) -> Self {
        Self {
            code,
            line: at.line,
            column: Some(at.column),
            validation: true,
        }
    }

    pub fn safe_message(&self) -> String {
        match self.column {
            Some(column) => {
                format!(
                    "{} at line {}, column {}",
                    self.code.summary(),
                    self.line,
                    column
                )
            }
            None => format!("{} at line {}", self.code.summary(), self.line),
        }
    }
}
