---
name: python-testing
description: Write deterministic Python unit and integration tests with fixtures, parameterization, isolated state and meaningful regression coverage.
source: https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/python-testing
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Python testing

Use the repository's configured runner: pytest, unittest or existing assert-based
checks. Do not add a framework or churn dependencies solely for this skill.
Executing tests runs project code and requires the harness's existing approval.

## Structure and assertions
- Test observable behavior with arrange/act/assert and descriptive names.
- Use parameterized cases for equivalent scenarios; keep failures attributable to
  one input. Assert exact relevant values and error types, not just truthiness.
- Cover normal behavior, meaningful boundaries, malformed external input and
  important cleanup/failure paths. A regression test must catch the original bug.
- Keep tests small and independent. Do not weaken assertions or skip failures to
  satisfy coverage numbers; coverage is evidence of execution, not correctness.

## Isolation
Use tmp_path/TemporaryDirectory for unique files; never fixed temp.txt or /tmp paths.
Restore patched environment, clock, globals and fixtures after each test. Patch
where the dependency is looked up, and use autospec where it catches API misuse.
Avoid mocking the code being tested or duplicating its algorithm in the expectation.

Unit tests must not depend on live DBs, network, credentials or paid models. Mock
external boundaries or use local fakes. Integration tests require a clearly named
disposable target and explicit execution approval; verify the target before any
DDL or cleanup. A nested transaction rollback is not guaranteed isolation if
application code opens other connections or commits outside the fixture.

## Concurrency and time
Test races with barriers/events or deterministic scheduling where practical, not
arbitrary sleeps. Give background workers and server fixtures bounded lifetimes and
clean them up in finally blocks. Use fake time for deadlines/retries; retain real
timeout tests only where the boundary itself is under test.

## Verification
Run the smallest reproducer, then the relevant suite on the final state. Read exit
status and all outcomes, including skipped, xfailed and timed-out cases. For flaky
behavior preserve the first failure and use a predeclared bounded retry plan rather
than retrying until green. Report commands and counts actually observed; if execution
is blocked, deliver tests but explicitly state they were not run.
