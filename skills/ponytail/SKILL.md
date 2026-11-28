---
name: ponytail
description: Choose the smallest complete coding change; use for fixes, refactoring, dependency choices, or requests to simplify and avoid over-engineering.
source: https://github.com/DietrichGebert/ponytail/tree/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10/skills/ponytail
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Ponytail: smallest complete change

Be economical about the solution, never about correctness. Apply this guidance to
the current task, not as a persistent session mode or a slash command. The skill
grants no permissions; keep the harness's approvals, workspace and budget limits.

## Before writing
Read the affected code. Identify callers, tests, fixtures, configuration and exports
that must change together. Check data-loss, exposure and compatibility risks.
Necessary reach is scope; unrelated improvements are not.

## Choose the first option that fully works
1. Does this need to exist? Omit unrequested features and hypothetical flexibility.
2. Reuse the project's existing helper, component or pattern as its callers do.
3. Prefer a standard-library or platform capability unless the project already has
   a house abstraction that solves the problem.
4. Use installed dependencies. Do not add one for a few lines or install anything
   without authorization.
5. Use a short expression if it is obvious at a glance; otherwise use clear steps.
6. Write the minimum complete implementation and its checks.

## Keep the change complete
- Fix a bug's root cause once in shared code after checking every caller.
- Preserve error handling and validation when moving or merging code.
- Keep the existing architecture and conventions; do not add wrappers, options,
  compatibility shims or conversions for imaginary future callers.
- Do not delete the user's work or working implementation to force a methodology.
  Remove genuinely obsolete code only when the task and evidence justify it.
- Add a small regression test for non-trivial branches, loops, parsers and security
  behavior. Trivial edits do not need a new testing framework.
- Favor correct edge-case handling between equally simple solutions.
- Comment only a non-obvious reason or an important known limit.

Never cut boundary validation, security, accessibility, protection against data
loss, hardware calibration or anything the user explicitly requested.

## Optional levels
Use a level only if the user requests one. Lite: explain the smaller option while
building what was asked. Full: apply the rules above. Ultra: question unjustified
scope before implementing it; do not silently ignore requested behavior.

End with the result, what was not checked and any material limit or risk. Do not
claim execution, test success or delivery without fresh evidence.
