#![no_main]

use libfuzzer_sys::fuzz_target;
use msgspec_toon_fuzz::error::{Fault, FaultCode, Position};
use msgspec_toon_fuzz::event::{Consumer, ScalarToken, StringToken};

#[derive(Default)]
struct Integers(Vec<i64>);

impl Consumer for Integers {
    fn start_object(&mut self, at: Position) -> Result<(), Fault> {
        Err(Fault::validation_at(FaultCode::TypeMismatch, at))
    }
    fn key(&mut self, _: StringToken<'_>, at: Position) -> Result<(), Fault> {
        Err(Fault::validation_at(FaultCode::TypeMismatch, at))
    }
    fn end_object(&mut self, at: Position) -> Result<(), Fault> {
        Err(Fault::validation_at(FaultCode::TypeMismatch, at))
    }
    fn start_array(&mut self, _: usize, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn end_array(&mut self, _: Position) -> Result<(), Fault> {
        Ok(())
    }
    fn scalar(&mut self, token: ScalarToken<'_>, at: Position) -> Result<(), Fault> {
        let ScalarToken::Integer(text) = token else {
            return Err(Fault::validation_at(FaultCode::TypeMismatch, at));
        };
        let text = std::str::from_utf8(text)
            .map_err(|_| Fault::validation_at(FaultCode::TypeMismatch, at))?;
        let value = text
            .parse::<i64>()
            .map_err(|_| Fault::validation_at(FaultCode::TypeMismatch, at))?;
        self.0.push(value);
        Ok(())
    }
}

fn canonical(values: &[i64]) -> Vec<u8> {
    let mut out = format!("[{}]:", values.len()).into_bytes();
    if !values.is_empty() {
        out.push(b' ');
        for (index, value) in values.iter().enumerate() {
            if index > 0 {
                out.push(b',');
            }
            out.extend_from_slice(value.to_string().as_bytes());
        }
    }
    out
}

fuzz_target!(|data: &[u8]| {
    let values: Vec<i64> = data
        .chunks_exact(8)
        .take(256)
        .map(|chunk| i64::from_le_bytes(chunk.try_into().unwrap()))
        .collect();
    let wire = canonical(&values);
    let mut decoded = Integers::default();
    msgspec_toon_fuzz::parser::parse(&wire, true, 2, &mut decoded).unwrap();
    assert_eq!(decoded.0, values);
    assert_eq!(canonical(&decoded.0), wire);
});
