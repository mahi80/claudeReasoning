---
name: verification-before-completion
description: Verify fresh command output and requirement coverage before claiming a fix, passing tests or completed delivery.
source: https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/verification-before-completion
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Evidence before completion claims

1. Identify what proves each claim: tests, compiler, artifact checks or a user flow.
2. Run the complete relevant check on the final working state, within existing
   operator approvals and budgets. Do not enable auto-approval or spend on live
   services to satisfy this skill.
3. Read output and exit status. Account for failed, skipped, timed-out and missing
   cases; a truncated log or a filtered success line is not complete evidence.
4. Compare the result to the acceptance criteria. Passing tests alone do not prove
   every requirement is implemented.
5. Report the actual result and material limits. If execution is denied or blocked,
   say checks were not run; do not claim success from confidence or static review.

| Claim | Necessary evidence |
|---|---|
| Tests pass | Fresh relevant suite, complete counts, no failures |
| Build succeeds | The actual build exited successfully |
| Bug fixed | Original reproduction now passes and regression test detects it |
| UI works | Interaction in a browser, including relevant edge cases |
| Artifact delivered | File exists, reopens and contains expected content |
| Worker completed | Inspect its changes and independently verify the output |

Do not infer a build from a linter, all tests from one test, behavior from type
checking, or layout from document parsing. Never destructively revert the user's
work to prove a regression; use a scratch copy when checking the pre-fix behavior.

Before delivery, inspect the diff for unintended changes and exposed credentials.
Commit, push, deployment and PR creation still require explicit authorization;
verification does not authorize them. End with what changed, checks actually run,
and any remaining blocker rather than promising untested completion.
