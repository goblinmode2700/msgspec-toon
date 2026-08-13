#![no_main]

use libfuzzer_sys::fuzz_target;
use msgspec_toon_fuzz::error::{Fault, Position};
use msgspec_toon_fuzz::event::{Consumer, ScalarToken, StringToken};

#[derive(Default)]
struct Sink;

impl Consumer for Sink {
    type ObjectSelection = ();

    fn start_object(&mut self, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn key(&mut self, _: StringToken<'_>, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn end_object(&mut self, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn start_array(&mut self, _: usize, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn end_array(&mut self, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn scalar(&mut self, _: ScalarToken<'_>, _: Position) -> Result<(), Fault> {
        Ok(())
    }
}

fuzz_target!(|data: &[u8]| {
    let mut sink = Sink;
    let result = msgspec_toon_fuzz::parser::parse(data, true, 2, &mut sink);
    if std::str::from_utf8(data).is_err() {
        assert!(result.is_err());
    }
});
