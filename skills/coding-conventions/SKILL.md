---
name: coding-conventions
description: File size, tests, naming and safety conventions for code the delivery agent writes; load before writing or changing code.
---

# Coding conventions

## Shape
- One concern per file, under about 150 lines. When a file grows past that, split it
  into a package or a helper module and keep the public names importable from the old
  place.
- Functions under about 30 lines, with a docstring that says what and why.
- Tests live next to the code or under tests/, one test module per module, named
  test_<module>.py (or <module>.test.js). Every bug fix adds the test that would have
  caught it.

## Working method
- Read a file before you change it; edit_file needs the exact text you saw.
- Prefer edit_file for small changes and write_file for new files or for rewrites of
  files you have read completely.
- Run the configured checks after each change. Fix the first failure, then run again.
- Keep the working tree committable: no scratch files, no debugging prints left behind,
  no generated caches added by hand.

## Safety
- No secrets, tokens, keys or passwords in code, tests, fixtures or documentation.
- No network calls in tests; mock or fake them.
- Validate input at the boundary; fail with a clear message rather than a traceback.
- Do not weaken a failing test, delete it or mark it skipped to pass a check. If a test
  is wrong, fix it and say so in the commit message and in .agent/pr.md.

## Commit messages
Subject under 70 characters in the imperative ("Add order totals endpoint"), a blank
line, then why and what was tested. One feature per commit where practical.
