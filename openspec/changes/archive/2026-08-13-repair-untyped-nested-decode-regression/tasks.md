## 1. Reproduce and cover

- [x] 1.1 Reproduce nested-record and irregular results against `v0.2.0b5` with the ten-worker mean.
- [x] 1.2 Add both shapes to the permanent release guard.
- [x] 1.3 Add generated evidence requirements for per-shape untyped results.

## 2. Repair

- [x] 2.1 Test one falsifiable repeated-key-cache hypothesis.
- [x] 2.2 Keep the repair only if both negative shapes improve and protected shapes do not regress.

## 3. Qualify

- [x] 3.1 Run `make check`, corpus, G2, G3, and G5.
- [x] 3.2 Run the complete release guard and regenerate evidence.
- [x] 3.3 Correct the release wording and publish a new beta hotfix only after all gates pass.
