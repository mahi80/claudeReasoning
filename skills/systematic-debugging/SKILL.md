---
name: systematic-debugging
description: Diagnose bugs, test failures, build problems and unexpected behavior from reproducible evidence before changing code.
source: https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Systematic debugging

## 1. Establish evidence
Read the full error, stack and failing assertion. Record exact reproduction steps,
inputs, expected behavior and actual behavior. Check relevant diffs, versions and
configuration. If reproduction is unreliable, describe that uncertainty rather
than presenting a guess as the root cause.

For a multi-component path, trace values backwards across each boundary until the
bad input or assumption first appears. Add temporary diagnostics only where needed.
Log types, counts and presence, not secrets, credentials or private request bodies.
Never dump the environment. Read-only diagnostics can still need shell approval;
do not switch commands or enable auto-approval after a denial.

## 2. Compare a working path
Locate the closest working example in the repository. Compare inputs, configuration,
ordering and ownership of state. Identify which differences explain the failure.
Check the installed dependency version before copying an external API example.

## 3. Test one hypothesis
State a specific cause and the evidence supporting it. Change one variable or add
one narrowly scoped test. If it fails to support the hypothesis, discard the theory,
not the data. Do not combine speculative fixes or repeatedly rerun unchanged work.
For an order-dependent test, isolate the relevant preceding cases with a bounded
local experiment; do not execute unreviewed polluter-finding scripts.

## 4. Fix and verify
Add the smallest regression test for the original symptom, fix its cause once, and
run the focused test plus relevant existing checks with approval. Keep boundary
validation and data-loss protections intact. Remove temporary diagnostics you added.
If several hypotheses fail, re-examine the model of the system rather than adding
another workaround. Report the root-cause evidence, changed behavior and exact
verification result; distinguish an environmental blocker from a code regression.
