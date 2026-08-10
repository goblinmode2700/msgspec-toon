//! The production parser core, compiled without the PyO3 boundary.

#[path = "../../src/error.rs"]
pub mod error;
#[path = "../../src/event.rs"]
pub mod event;
#[path = "../../src/header.rs"]
pub mod header;
#[path = "../../src/limits.rs"]
pub mod limits;
#[path = "../../src/parser.rs"]
pub mod parser;
#[path = "../../src/scalar.rs"]
pub mod scalar;
#[path = "../../src/scan.rs"]
pub mod scan;
