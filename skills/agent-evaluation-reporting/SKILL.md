---
name: agent-evaluation-reporting
description: Report AI-agent evaluations with distinct autonomous, assisted, failed, timeout and invalid outcomes, honest denominators and decision gates.
source: https://github.com/sickn33/antigravity-awesome-skills/tree/560a2b034d8ce3eb90445841ab6a53df7132926a/skills/agent-evaluation-reporting
license: CC-BY-4.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Agent evaluation reporting

Adapted from Agent Evaluation Reporting by Whxuan0701 in AAS. Interpret supplied
results; do not invent missing evidence, install providers or launch paid runs.

## Comparison contract
Record task sampling, model/provider, prompt/policy, tools, harness, rubric, timeout,
retry policy, budgets, environment and human-intervention policy. If material
conditions differ, label the comparison non-equivalent rather than claiming the
candidate caused the difference.

## Mutually exclusive attempt ledger
Classify every executed attempt once:
- autonomous_success: verified completion without human intervention.
- assisted_success: completion only after a human intervened.
- failure: terminal evaluable failure.
- timeout: exhausted declared time/step budget.
- invalid: no valid evaluation due to infrastructure, input or evaluator failure.

Retain attempt/task IDs, retry index and parent, configuration, intervention count,
duration, observed cost, reason and redacted evidence. Reconcile scheduled cases
with executed attempts and explicitly report unrun cases. Preserve retries and
first failures. Roll up each unique task once; do not derive eventual completion
without retry lineage and a predeclared retry policy.

## Denominators
N_all = all executed attempts; N_eval = N_all - N_invalid.
T_all = unique scheduled tasks; T_eval = tasks with a valid final outcome under the
fixed retry policy. Show counts alongside every rate:
- autonomous attempt success: N_autonomous / N_eval.
- assisted attempt success: N_assisted / N_eval.
- attempt non-completion: (N_failure + N_timeout) / N_eval.
- invalid-attempt rate: N_invalid / N_all.
- first-attempt task completion: T_first_completed / T_all.
- eventual task completion: T_eventual_completed / T_eval.
- operational delivery: T_eventual_completed / T_all.

Zero denominators mean unavailable/inconclusive, never 100% or a division error.
Check population sums. An attempt rate is not task/workflow completion.

## Latency, cost and decisions
Separate autonomous completion, assisted end-to-end latency and failure time to
terminal. Never average subgroup medians into an overall median. Overall percentiles
require per-run observations and an explicit timeout/censoring policy. Unknown
cost/duration remains unknown. Report retry overhead and attempts per task.

State sample sizes, uncertainty and critical violations. Apply predeclared gates
individually as pass/fail/inconclusive; critical safety failures cannot be averaged
away. With missing thresholds/evidence, readiness is not determined. A finite,
possibly biased test set is not proof of production reliability. Redact private
inputs and credentials; publication still requires authorization.
