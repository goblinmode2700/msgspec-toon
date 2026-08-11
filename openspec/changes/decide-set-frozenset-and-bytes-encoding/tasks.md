## 1. Reproduce and Decide

- [ ] 1.1 Add executable probes for set, frozenset, bytes, and their projected forms.
- [ ] 1.2 Rerun the probes after the `0.3.0b1` encoder-decision checkpoint.
- [ ] 1.3 Record the direct bytes representation and set-order constraints.
- [ ] 1.4 Decide native support or intentional refusal for each type.

## 2. Implement the Ruling

- [ ] 2.1 Implement direct base64 bytes encoding if exact parity and performance permit it.
- [ ] 2.2 Implement set-like encoding only if one total canonical order is specified.
- [ ] 2.3 Add static supported-route guidance for each refusal.
- [ ] 2.4 Add cross-process, mixed-element, hook, and payload-safety cases.

## 3. Qualify

- [ ] 3.1 Run focused encode A/B and canonical byte and token locks.
- [ ] 3.2 Run `make check`, corpus, G2, G3, G5, and strict OpenSpec validation.
- [ ] 3.3 Update the support matrix, README, report, and changelog.
- [ ] 3.4 Archive this change only after its ruling is released.

