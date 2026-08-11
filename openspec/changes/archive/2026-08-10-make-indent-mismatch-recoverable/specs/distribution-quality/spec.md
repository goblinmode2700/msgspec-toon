## ADDED Requirements

### Requirement: Indentation option compatibility is release evidence

The executable release suite SHALL round-trip both nested mappings and tabular arrays with
matching indentation widths 1, 2, and 4. It SHALL separately prove that mismatched default decode
reports the observed width and that all pinned official indentation-error fixtures retain their
declared outcomes. A rejected inference candidate and its same-session timing SHALL remain in the
private optimization record rather than be claimed or published as adopted behavior.

#### Scenario: Width matrix cannot regress silently

- **WHEN** release qualification runs
- **THEN** functional and reusable decoders round-trip nested and tabular documents at matching
  widths 1, 2, and 4
- **AND** mismatches report the observed width

#### Scenario: Corpus rules remain authoritative

- **WHEN** the pinned official fixture corpus supplies an indentation size
- **THEN** the decoder uses that explicit value
- **AND** every strict indentation-error fixture retains its declared result

