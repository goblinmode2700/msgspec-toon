---
name: "Last Mile"
description: "Run one or more proven last-mile codec iterations"
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(git:*), Bash(make:*), Bash(uv:*), Bash(cargo:*), Bash(openspec:*)
category: "Workflow"
tags: ["rust", "python", "performance", "conformance"]
---

Run the native iteration loop in `LAST-MILE.md`.

Read these files before work:

1. `CLAUDE.md`
2. `HANDOFF.md`
3. `docs/adversarial-review-v0.2.0.md`
4. `LAST-MILE.md`

Select the first unblocked queue item unless the user names another item.
State the item and one falsifiable hypothesis.

Continue through queue items until a stop condition occurs or the user interrupts.
Use one focused checkpoint commit for each proven item.

For each item:

1. Add a failing adversarial, differential, or measurement test.
2. Make the smallest focused change.
3. Run the required gates from `LAST-MILE.md`.
4. Reject any change that regresses a protected gate.
5. Update evidence, `LAST-MILE.md`, and `HANDOFF.md`.
6. Commit the proven checkpoint.

Do not create a wrapper, daemon, worktree manager, or agent harness.
Do not skip same-session A/B for a performance claim.
Do not change canonical bytes without a conformance requirement.
Do not mark work complete from code inspection alone.

At a stop condition, write the exact blocker and preserve all evidence.
