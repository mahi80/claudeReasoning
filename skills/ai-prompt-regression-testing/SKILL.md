---
name: ai-prompt-regression-testing
description: Compare prompt changes on fixed cases with recorded model settings, mandatory checks, missing-result handling and case-level regression evidence.
source: https://github.com/sickn33/antigravity-awesome-skills/tree/560a2b034d8ce3eb90445841ab6a53df7132926a/skills/ai-prompt-regression-testing
license: CC-BY-4.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Prompt regression testing

Adapted from AI Prompt Regression Testing by Ranjeet2063, published in the AAS
repository. This is evaluation procedure only: no provider adapter, judge or dataset
is installed. Commands, live models and external services retain approval/budget
boundaries; start with local deterministic fixtures.

## Matched comparison
1. Freeze representative case IDs, dataset revision, supplied facts, required
   behavior and forbidden outcomes before changing the prompt.
2. Record baseline/candidate prompt digests, exact model/version, actual inference
   settings, tools and environment. Do not silently swap models or settings.
3. Predeclare checks and acceptance criteria: schema/fields, behavior and tool
   authorization first; reviewed rubrics for open text when needed.
4. Run both sides under the same budget and permissions, preserving every attempt.
   Missing output, timeout or judge failure is incomplete, never a pass or a
   fabricated zero-cost observation.
5. Review differences per case, keeping mandatory safety and schema failures
   visible even if average similarity improves.

## Judge limitations
Use deterministic verification for executable behavior where possible. Similarity
and embeddings do not prove factual or code correctness. If an LLM judge is
explicitly approved, record its version/rubric, blind/randomize presentation and
calibrate on reviewed examples. Preserve ties as ties and validate reversed-pair
scoring before interpreting pairwise wins. Do not ask a judge to verify hidden
reasoning or treat confidence as objective correctness. The reviewed OpenJudge
pairwise helper is not imported because tie/swap behavior was incorrect.

## Regression register
Each attempt needs case_id, dataset revision, prompt revision, model/runtime,
check, result (pass/fail/incomplete), redacted evidence reference and observed
latency/cost or null if unknown. Use stable textual IDs across JSON/CSV/SQL.

Validate exact expected case inventory: reject duplicate/unexpected IDs and unknown
statuses, retain known failures when other cases are incomplete. All recorded checks
passing means only those checks passed; it is not a general quality certificate.

Report denominators, failed cases, incomplete results and uncertainty. Apply the
predeclared decision rule, not a post-hoc threshold. Keep reports at an authorized
workspace destination without private prompts, user content or credentials.
Deployment and publication require separate approval.
