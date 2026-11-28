---
name: test-driven-development
description: Add behavior through a focused failing test, a minimal implementation and verified refactoring; use for features and bug fixes.
source: https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/test-driven-development
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Test-driven development

Use the repository's existing test tools. A skill is not permission to run commands,
install dependencies, remove code or weaken approval and budget limits.

## Red
- Identify one observable behavior and its acceptance condition.
- Write a small deterministic test using public behavior rather than internal
  implementation details. Name the scenario and expected result clearly.
- Run it with approval. Confirm it fails because the behavior is missing, not
  because imports, setup, syntax or dependencies are broken.
- For a bug, use the smallest input that reproduces the original symptom.
- If implementation already exists, keep it: use an isolated scratch copy or a
  targeted mutation to demonstrate the test catches the missing behavior. Never
  delete working code or discard uncommitted work to manufacture a red phase.

## Green
Write the simplest correct implementation that satisfies the test. Avoid unrelated
cleanup, future configuration and new abstractions. Keep validation and protections
at trust boundaries. Run the test and nearby existing tests, reading full output
and exit status; do not treat absence of an error line as success.

## Refactor
Only while checks are passing, improve necessary clarity without changing behavior.
Run the tests again. Prefer a few clear lines over premature shared infrastructure.

## Useful cases
Cover normal input, meaningful boundaries, malformed external input and the failure
path. Stub network, clock and external services at the boundary; do not mock away
the behavior under test. Use isolated temporary directories instead of fixed files.
Never require a real database, deployment or paid model for an offline unit test.

When execution is unavailable, provide tests and implementation but state that the
red/green cycle was not run. Do not skip, weaken or delete a failing test merely to
make the result pass; correct a demonstrably wrong test and explain why.
