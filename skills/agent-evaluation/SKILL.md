---
name: agent-evaluation
description: Design reproducible AI-agent regression evaluations with frozen cases, explicit verifiers, permission boundaries and bounded repeated runs.
source: https://github.com/sickn33/antigravity-awesome-skills/tree/560a2b034d8ce3eb90445841ab6a53df7132926a/skills/agent-evaluation
license: Apache-2.0 upstream; CC-BY-4.0 AAS modifications; adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Agent evaluation

Adapted from Vibeship Spawner Skills and AAS maintainers. AAS revised this content
on 2026-09-05 to remove unsupported benchmark claims and clarify uncertainty and
failure classification. This adaptation is instruction-only, with no provider,
judge, dataset or runnable evaluation suite bundled.

## Freeze the evaluation contract
Record case IDs and dataset revision, expected observable outcomes, forbidden
operations, baseline/candidate revisions, model ID/version, inference settings,
prompt digests, tool/runtime versions, target environment and repeat order. Predeclare
budgets, stopping rules and decision criteria. Use synthetic or approved redacted
inputs and isolated fixtures; do not access accounts or spend on live models without
separate authorization. A completed prior budget is not reusable permission.

## Validate the evaluator first
Run known-pass, known-fail and deliberate evaluator/infrastructure-failure fixtures
with approved local execution. Ensure classification and retention are correct.
Exceptions, missing outputs and timeouts are not evidence of safe rejection.
Critical authorization/safety failures must remain independent of average quality.

## Run matched cases
Use the same case definitions and bounds for baseline and candidate, from clean
fixture state. Preserve every attempt, run ID, reason, latency, resource totals and
redacted evidence. Do not retry until green, drop the first failure or change the
expected output to fit the candidate.

## Compare and investigate
Separate wrong behavior, expected safe refusal, infrastructure outages, evaluator
faults and state contamination. A verifier fault makes affected results inconclusive,
not agent success. Review regressions case by case and retain the original evidence.
A changed expectation requires a reviewed contract revision and reruns of both sides.

Repeated runs of one case are correlated, not independent task-distribution samples.
Use case-level/clustered uncertainty when appropriate; ten successful trials do not
prove 100% reliability. Small samples or absence of significance do not establish
production readiness or equivalence.

## Decide and verify a fix
Return pass/fail/inconclusive against predeclared gates. Any critical forbidden
operation fails its safety gate even if aggregate quality improves. After a bounded
fix, recheck the original failure then the relevant frozen suite from clean state.
Stop at the approved budget and report unresolved work. Publication and deployment
are separate decisions; a passing evaluation is not permission to release.
