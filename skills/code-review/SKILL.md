---
name: code-review
description: Review a branch, PR or working diff against repository standards and the requested specification, with evidence-backed findings.
source: https://github.com/mattpocock/skills/tree/bbadaa631c37af594e5a05c9cefacd9956136b18/skills/engineering/code-review
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Two-axis code review

Review first; do not modify, publish or merge unless requested. Tool use and any
optional delegation remain constrained by the harness's allowlist and budget.
A skill does not grant access to an issue tracker or install its integration.

## Establish the comparison
Resolve the requested base ref and record its commit. For branch work, inspect
base...HEAD and base..HEAD commits. For uncommitted work, include staged and
unstaged diffs and relevant untracked files. Do not silently exclude local edits.
Read changed functions and their callers, not just diff hunks.

Find the specification in the user's request, an available issue or repository
specification. Read repository contribution and coding standards. If the spec is
unavailable, mark that axis unassessed instead of inventing requirements.

## Standards axis
Check correctness, security boundaries, lifecycle cleanup, concurrency, error paths,
tests and documented conventions. Code smells are heuristics, not automatic bugs:
unclear names, duplication, speculative abstractions, scattered responsibilities,
message chains or wrappers matter only when they cause a concrete problem.
Repository conventions override generic stylistic preferences. Do not recommend
refactoring solely because a function exceeds an arbitrary size.

## Specification axis
Check each requirement for implemented behavior, missing edge cases, changed
contracts and unrequested scope. Verify claims against actual code or reproduction;
a successful agent summary or a green unrelated suite is not evidence.

These axes may be reviewed serially. If scoped workers are available, delegate only
when beneficial and pass the base, relevant files and criteria; do not require
parallel agents or fresh-session tooling that the harness does not offer.

## Report
Separate standards and specification findings. For each material finding give
severity, file:line, concrete triggering conditions, impact and a minimal remedy.
Distinguish verified defects from uncertain risks and subjective suggestions.
State checks performed and those not run. No findings means no findings within
the reviewed scope, not proof of security or authorization to merge.
