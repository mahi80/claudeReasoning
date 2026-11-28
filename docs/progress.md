# Progress and handoff — 28 November 2026

This is a dated coordination snapshot, not a claim that every tested change is on
`main`. The goal is a task executor with planning, scoped workers, lazily loaded skills,
approved MCP/tools, verification and code-gated delivery; proprietary-model parity is
not measured. [Back to README](../README.md).

## Available on GitHub

| Location | Completed work | Status |
|---|---|---|
| `main` at `440c409` | PR #1: runtime/approval safety, scoped delegation, configured MCP and shared budgets | Merged |
| `main` at `440c409` | PR #2: five-stage delivery runner, guarded checks/commits/push and ADR gates | Merged |
| `main` at `440c409` | PR #3: Apache 2.0 project license | Merged |
| `main` at `440c409` | PR #4: 19th `make-tests-pass` eval, `--delivery` checks without git tools, isolated Python graders, pipeline/quality stage tests | Merged |
| `skills-import` at `18af506` | Original 33 compact instruction-only imports; eight originals preserved | Historical published branch, not merged; use PR #9 instead because this branch lacks lazy discovery and root NOTICE updates |
| `readme-progress` | This progress document and the README link | Documentation-only branch; runtime and skills fixes are not included |
| `pod-lifecycle-fixes` at `0c93753` | Standalone pod lifecycle fixes, based on `main` without skills | [PR #5](https://github.com/mahi80/claudeReasoning/pull/5) open; 305/305 offline checks/tests passed; not merged |
| `reviewer-evidence-checkpoints` at `d055fe8` | Read-only reviewer paging and checkpoint journals, based on `main` without skills or pod fixes | [PR #6](https://github.com/mahi80/claudeReasoning/pull/6) open; 323/323 offline checks/tests passed; not merged |
| `eval-outcomes-trace` at `8711797` | Five-outcome eval reporting, per-process trace lock and regression tests, based on `main` without other runtime concerns | [PR #7](https://github.com/mahi80/claudeReasoning/pull/7) open; 313/313 offline checks/tests passed; not merged |
| `main` at `c21cd17` | Offline test discovery/runner and Windows/Linux/browser CI, proposed by the other instance | [PR #8](https://github.com/mahi80/claudeReasoning/pull/8) merged; newest main CI run 46123741330 failed |
| `skills-library` at `9f6fd43` | All 41 skills, bounded on-demand imported-library discovery and complete root NOTICE attribution, based directly on `main` | [PR #9](https://github.com/mahi80/claudeReasoning/pull/9) open; 307/307 offline checks/tests passed; not merged |

Main now also includes PR #8 at `c21cd17`; that merge was performed outside this instance.
PRs #5–#7 and #9 remain open. Review each concern independently; do not merge the older
`skills-import` branch instead of PR #9.
The three runtime PRs and PR #9 are each based directly on `main` at `440c409` and do
not inherit one another. Original worktrees and published branches remain intact.

## Coding product milestone 1 — shared executor

User direction: primarily coding tasks, entered through chat or a terminal, using
DeepSeek on a planned four-H200 inference service for up to ten users, without daily
user token/task quotas. GPU scheduling, tenant isolation and deployment remain separate
work; no GPU was provisioned and no hosted access was enabled.

A new local `coding-chat-cli` branch starts directly from current main `c21cd17`, without
unmerged runtime/skills PRs. Its source is still uncommitted and not published remotely.
The existing worktrees remain untouched.

- Added `harness/coding.py`: one coding workflow for both forthcoming interfaces,
  using the configured OpenAI-compatible/vLLM endpoint, existing skills, explicit worker
  grants and optional operator-configured MCP tools.
- Coding inspects files, plans and implements work. Programs run only through trusted
  operator-configured checks; coding does not receive arbitrary shell or git publication
  tools. No automatic dependency installation, commit, push or deployment is enabled.
- The config stays outside the editable workspace and must name at least one gate check.
  Required checks are rerun after implementation, and a fresh read-only reviewer must
  return PASS before the result is accepted. Failed/missing checks, stopped execution,
  blank reports and missing/failed review verdicts cannot become accepted results.
- Implementation, checks and review share one existing per-run execution budget; no
  daily user quota was added. Existing context/runaway safeguards remain while durable
  continuation and fair hosted scheduling are developed.
- Focused validation: **12/12 coding executor tests passed**, including real file tools,
  scoped delegation, actual isolated Python check execution and fixture-model review;
  failing gates, review failures, budget stops, secret-safe exceptions and configuration
  confinement are covered. Full current-main regressions are running separately.
- Next milestone: wire chat coding mode and an interactive/one-shot terminal client to
  this executor, test HTTP/CLI and the in-app browser, then publish another handoff.
  The current app has no tenant authentication or container isolation and is not safe
  for public multi-user hosting.

## Skills cost and license milestone

PR #9 contains two commits: the original reviewed import cherry-picked onto a fresh
main-based branch, followed by the discovery/NOTICE fix. No upstream executables,
installers, hooks, assets, datasets, dependencies or cloud integrations were installed.
Office generation, rendering and spreadsheet recalculation have not been validated.

Measured offline against the installed 41-skill pack:

| Measurement | UTF-8 bytes |
|---|---:|
| Original complete index (41 skills) | 6,161 |
| Original eight-skill index | 1,146 |
| Imported metadata added by the old index | 5,015 |
| New initial index, including discovery hint | 1,287 |
| New discovery tool schema alone | 536 |
| Representative initial system/task/tool-schema payload before | 12,126 |
| Same representative payload after | 7,802 |
| Net initial payload saving, including schema changes | 4,324 (35.7%) |

These are serialized byte measurements, not exact model tokens. The medium-effort
4,096-token reply limit is unchanged and is not the request's prompt budget. Payload
percentages vary with conversation history. Discovery and loaded instructions still
consume request/run budgets when used.

- Imported skill bodies/descriptions are not read into the initial index. Originals
  and custom skills retain their existing visibility, including custom directories
  without an import manifest.
- `find_skills(query, offset)` searches installed names/descriptions on demand. Empty
  query browses; all query words must match. Each valid JSON page contains at most five
  entries and 3,500 serialized bytes, with a continuation offset. The model then uses
  `load_skill` for the selected full instructions.
- Delivery stages can discover skills. Workers get discovery only through an explicit
  parent tool grant; a load-only worker is not told to use a tool it lacks. Finding or
  loading a skill never grants command, MCP, account or cloud permissions.
- Root NOTICE identifies every imported source and license, links the full attribution
  and modification notices, preserves the AWS notice, and identifies MPL-2.0 source
  terms and CC BY 4.0/AAS attribution. The eight original skills are not upstream imports.
- All six standalone scripts exited 0 on Windows with Python 3.14.3: harness 126,
  evals 7, eval_cases 51, app 34, delivery 70, skills 19; **307/307** total checks/tests.
  Skill regressions cover cost, original/custom compatibility, discovery/full loading,
  pagination, Unicode, invalid arguments, scoped grants, NOTICE, and mock-model tool
  dispatch. No model/GPU/browser/cloud calls or Office artifact production were used.

## Preserved local runtime integration

The local `runtime-reliability` branch is based on merged `main` at `440c409`, with the
original skills import and these uncommitted changes applied:

- **Pod lifecycle:** fail promptly on rejected starts, request idle shutdown even when
  `/health` is down, recheck activity under the lock, deduplicate accepted stops, restart
  after a stop request, retain restart state through rejected/failed starts, and keep
  the watchdog alive through transport failures. API acceptance is not proof of physical
  GPU shutdown; these checks used mocks only.
- **Reviewer evidence:** immutable, read-only review snapshots with bounded index/record
  paging. Coordinator reasoning and extra permissions are not exposed; results clipped
  at the original tool boundary remain incomplete.
- **Checkpoint journals:** format 2 snapshots reference an append-only observation
  journal by record count and SHA-256. Resume verifies the committed prefix, preserves
  genuine repeated calls without duplicating evidence, and leaves crash tails untouched.
  Journals and in-memory evidence still grow; there is no retention cap or hard snapshot
  size limit. Older checkpoint formats require a fresh task run.
- **Eval outcome ledger:** runner-assigned `pass`, `fail`, `invalid`, `timeout` and
  operator-declared `assisted`. Only unassisted passes count in `pass_rate`, over all
  attempts; assistance does not hide failure or timeout. Empty shards report no pass
  rate, and failed/stopped executions cannot pass an artifact-only grader.
- **Trace integrity:** serialize JSONL appends across threads in one process, preventing
  parallel workers from losing/interleaving records on Windows. Parallel processes
  still need separate trace paths. The queued-approval deadline test now simulates
  expiry deterministically; runtime approval behavior was not changed.

This combined local integration remains uncommitted and is not a remote branch. Its
concerns were published separately in PRs #5, #6 and #7, each without the skills import.
PR #6 changes the checkpoint format; it does not add evidence retention or OS isolation.
The new PR #9 discovery/NOTICE fix has not been applied to this preserved integration,
so its historical 374-check total does not include the new skill regressions.

The local integration applied cleanly and preserved both bots' mock-model scenarios;
there was no manual conflict resolution. Preserve both sets if a later integration
conflicts in the shared mock endpoint.

## Verification boundaries

The merged-main baseline passed **288 non-browser checks** on 28 November. README
baseline counts stay unchanged until corresponding code actually lands. Counts below
include script assertions and unittest methods, not benchmark tasks.

The historical combined snapshot passed **374/374 offline checks** across ten scripts
on Windows with Python 3.14.3. This is the uncommitted integration, not `main`, PR #9 or
this documentation branch:

| Script in the preserved local integration | Passing checks/tests |
|---|---:|
| `test_harness.py` | 131 |
| `test_evals.py` | 10 |
| `test_eval_cases.py` | 51 |
| `test_app.py` | 34 |
| `test_delivery.py` | 70 |
| `test_skills.py` | 9 |
| `test_pod_manager.py` | 17 |
| `test_review_evidence.py` | 13 |
| `test_checkpoints.py` | 17 |
| `test_eval_outcomes.py` | 22 |
| **Total** | **374** |

The first full run exposed a parallel trace-write failure; the next exposed the
clock-sensitive queued-approval test. Both were addressed, and all ten scripts then
exited successfully in the final run. The separate restart regression reproduced
rejected and transport-failed starts before its fix.

To reproduce the historical integration, activate an environment containing
`requirements.txt` dependencies, then run from that integration's repository root
(**not** the documentation-only branch):

```bash
for suite in harness evals eval_cases app delivery skills pod_manager \
             review_evidence checkpoints eval_outcomes; do
  NO_PROXY=localhost,.localhost,127.0.0.1,::1 \
    no_proxy=localhost,.localhost,127.0.0.1,::1 \
    python "tests/test_${suite}.py" || exit "$?"
done
```

These tests use local mock endpoints or fixtures; they do not start a paid GPU.

No new live-model/GPU run or browser rerun was performed by this instance for the
runtime or skills changes. The 27 November B300 evidence documented in the README and
[Runpod guide](../infra/runpod.md) predates them and the delivery runner; it does not
validate the new delivery stages or the full 19-case benchmark.

PR #8 reports local Windows/Linux and 22/22 browser checks from the other instance;
those claims were not independently reproduced here. GitHub's historical run 46112243942
showed all four jobs failed with no executed steps, and failed-job logs were unavailable.
PR #8 subsequently merged, and newest main run 46123741330 also reports failure. Treat
hosted CI as unresolved, not passing; the merged runner is reused rather than duplicated.

## Remaining work, in order

1. Adversarially review runtime PRs #5–#7 and skills PR #9; merge only with explicit
   approval. Keep the original combined worktree intact. Do not merge `skills-import`.
2. Resolve and review PR #8's hosted CI failures with its author. Its test discovery is
   intended to include new concern-specific suites when they land. No second CI driver
   is being created here; its local results remain attributed to the other instance.
3. After approved code lands, revalidate the actual merged integration and update README
   counts from that run, not by adding together overlapping PR totals. This snapshot
   has moved out of the README top and is linked from it.
4. Revalidate browser flows on the new integration and implement delivery-stage/chat
   integration. This instance's browser rerun remains pending.
5. Separately authorize bounded live-model delivery/eval validation and confirm actual
   pod shutdown, preserving failures and assisted results as well as successes.
6. Enforce host/container isolation and deployment budgets. Workspace checks and approvals
   are not an OS sandbox; model-token budgets do not cap GPU rental spending.
7. Rebuild and review the design document after the implementation settles.
