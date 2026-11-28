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
  confinement are covered. Subsequent regression results and fixes are recorded below.
- Next milestone: wire chat coding mode and an interactive/one-shot terminal client to
  this executor, test HTTP/CLI and the in-app browser, then publish another handoff.
  The current app has no tenant authentication or container isolation and is not safe
  for public multi-user hosting.

## Coding product milestone 2 — GitHub, GitLab and Jira connectors

User approved these integrations after milestone 1. The implementation is local on
`coding-chat-cli`, still uncommitted and unpublished; this documentation branch contains
none of the executable changes. Main remains `c21cd17`; PRs #5–#7 and #9 remain open.

- Added `harness/integrations.py` and an environment-name-only configuration example.
  GitHub/GitLab support repository file reads, issues/comments, branches, multi-file
  API commits, pull/merge requests, paged diffs, review/approval and explicit merging.
  Jira uses REST v3 for project-scoped issues, ADF descriptions/comments and transitions.
  GitLab approval is separate from GitHub's COMMENT/APPROVE/REQUEST_CHANGES review API.
- Operators specify provider API bases, credential environment-variable names, exact
  repositories/projects and a tool allowlist in an external configuration selected by
  `AGENT_INTEGRATIONS_CONFIG`. No credentials or endpoints are chosen by the model.
  Jira Cloud basic authentication uses a configured user environment variable; bearer
  authentication is also available. No OAuth onboarding or live account connection exists.
- Read tools run within their configured resource scope. Every write requires a distinct
  operator approval, even with `AGENT_AUTO_APPROVE=1`; unattended writes fail closed.
  Chat uses the existing per-prompt approval IDs. Terminal approval requires explicit
  `yes`; noninteractive one-shot execution denies writes rather than hanging.
- HTTP redirects are not followed; inherited proxy settings are not used. Credentials
  are attached only to the configured provider client and are excluded from tool schemas,
  model arguments and provider-error text. Provider failures do not automatically retry
  writes; partial/unknown outcomes require inspecting provider state first.
- Merges and reviews pin an expected commit SHA. GitHub commit publication is non-force
  and parent-pinned. GitLab checks the branch head and guards existing files with their
  last-commit IDs; this is not an atomic compare-and-swap of the entire GitLab branch.
  The connectors publish supplied UTF-8 file content through APIs, not arbitrary git
  shell commands; binary uploads, clones, rebases and force-push are not implemented.
- **24/24 connector unittest methods passed**, covering all 39 supported operations with
  mocked transports, approval denial/allow, auto-approval bypass prevention, exact scopes,
  argument/path/ref validation, authentication, redirect refusal, safe errors, pagination,
  expected-head guards, no force push, Jira ADF and shared deadlines. These are not live
  provider or GPU tests, and service-specific account policies remain unvalidated.
- Both interfaces are wired to these configured tools: focused terminal **10/10** and
  coding HTTP **12/12** tests pass. Browser accepted/rejected and approval/denial flows
  have been exercised with local fixtures; the complete regression rerun and final
  browser handoff are the next milestone.

No dependency was installed, no account was connected, no real issue/request was changed,
no GPU was provisioned and no new daily user quota was introduced. Configurations are
process-level, not tenant identities; this remains unsafe for public multi-user hosting.

## Coding product milestone 3 — chat and terminal, verified locally

The shared executor now has two consumers on the local `coding-chat-cli` branch:
`app/server.py` coding mode and `harness/code_cli.py` one-shot/interactive terminal use.
The source remains uncommitted and is not on GitHub. This is a local single-operator
milestone, not a deployed ten-user service or a remote authenticated terminal client.

- Configured chat defaults to Coding/high effort and streams plans, tool/worker progress,
  required-check outcomes, independent review and accepted/rejected/stopped/failed results.
  General chat remains available; its existing HTTP default stays medium. With no coding
  configuration, Coding is disabled and a direct coding request is rejected.
- When coding is configured, all chat tasks share one workspace lock, including General
  tasks, so they cannot edit during another coding task's final checks/review. This lock
  is in-process only: do not point concurrent CLI/server processes at the same workspace.
  It is not tenant isolation, a durable queue or fair H200 inference scheduling.
- Terminal supports one-shot tasks, successive interactive tasks, effort selection,
  per-task run IDs, one-shot checkpoint resume and structured result export outside the
  editable workspace. Each interactive task starts fresh model context over existing
  workspace files; there is no durable conversation history. Exit codes are 0 accepted,
  1 rejected, 2 stopped, 3 failed and 130 interrupted.
- Both consumers load operator-configured MCP and GitHub/GitLab/Jira tools. Checks and
  final read-only review still gate acceptance. Passing review does not authorize a push
  or merge: each connector write needs its own explicit decision. A declined integration
  action does not imply local coding failed; the final report must identify omitted work.
- Initial regressions exposed main's clock-sensitive queued-approval fixture; only its
  deterministic test correction from unmerged PR #7 was copied locally. A later run hit
  an SDK timeout just before the shared deadline. The runtime now classifies a
  deadline-shortened SDK timeout as a stopped time budget, without retries; normal
  600-second/unbounded provider timeouts remain failures. A deterministic regression
  covers both outcomes and reservation cleanup. No budget or approval limit was weakened.
- A first terminal test attempt used the wrong fixture API key and failed authentication;
  correcting the mock setup produced the results below. No live provider key was used.

Final continuous Windows/Python 3.14.3 run using the merged `tests/run_offline.py`:

| Script | Passing checks/tests |
|---|---:|
| `test_app.py` | 34 |
| `test_code_cli.py` | 10 |
| `test_coding.py` | 13 |
| `test_coding_app.py` | 12 |
| `test_delivery.py` | 70 |
| `test_eval_cases.py` | 51 |
| `test_evals.py` | 7 |
| `test_harness.py` | 126 |
| `test_integrations.py` | 24 |
| **Total: all nine scripts exited 0** | **347/347** |

These counts include assertions/unittest methods, not benchmark tasks. No Linux rerun,
real DeepSeek/H200 inference or real GitHub/GitLab/Jira account validation was performed.
Main README counts remain 288 until reviewed code lands and merged-main is revalidated.
Hosted CI run 46123741330 on main `c21cd17` still reports failure; local passes do not
change that status.

The internal browser was exercised against local model/provider fixtures: accepted
coding with actual generated files/check execution/review, failed-check rejection,
failed-review rejection, explicit connector approve/deny, General chat regression,
cleared input and escaped user/model text (zero injected scripts). The fixture was
restarted on the latest runtime and the accepted path rerun; the screenshot was viewed
and the current-page console had no warnings/errors. One earlier Windows Proactor socket
reset occurred on browser reload; it was not an application run failure. This manual
browser evidence is separate from the 347 offline checks and is not a live-model test.

### Operator run order after the source is reviewed and published

1. Set `AGENT_WORKSPACE` to the assigned repository and configure `LLM_BASE_URL`,
   `LLM_API_KEY`, `LLM_MODEL` and any model-card-specific thinking fields for the
   existing OpenAI-compatible/vLLM endpoint. Leave `RUNPOD_POD_ID` unset for an
   operator-managed always-on H200 service. Use the existing dependency environment.
   Chat additionally requires the authentication prerequisite in milestone 4 below.
2. Create an operator-owned checks JSON outside the editable workspace and set
   `AGENT_DELIVERY_CONFIG` to its absolute path. It needs a nonempty `checks` map and
   `gate` list. Each check has an operator-approved `argv` array and timeout; choose
   actual project tests/builds. The agent cannot edit this configuration or install
   dependencies automatically. Harness/interpreter/helpers must also remain outside
   the editable workspace. These constraints are not an OS sandbox.
3. Optionally copy `harness/integrations.example.json` outside the workspace, replace
   provider bases and resource placeholders, remove unwanted services/tools, export
   the credential environment variables and set `AGENT_INTEGRATIONS_CONFIG` to that
   external file. Jira Cloud uses the REST v3 base and `JIRA_EMAIL`/`JIRA_TOKEN`; GitLab
   uses its REST v4 base. Credentials are never model tool arguments. Existing optional
   MCP configuration remains selected by `AGENT_MCP_CONFIG`.
4. From the harness repository root, run either interface (substitute the interpreter
   from the existing environment):

   ```bash
   python harness/code_cli.py "Implement the requested feature and verify it"
   python harness/code_cli.py --interactive
   python harness/code_cli.py --run-id task-001 --resume "Continue the implementation"
   python -m uvicorn server:app --app-dir app --host 127.0.0.1 --port 8080
   ```

   Run only one process per workspace. Keep chat local or behind separately supplied
   authentication. Interactive terminal approval requires typing `yes`; piped/unattended
   one-shot tasks cannot publish. Checkpoint resume covers the agent implementation,
   not a durable accepted-result ledger or completed external-write replay policy.
5. Reproduce the non-browser regression with `python tests/run_offline.py`. To exercise
   the coding UI without accounts or GPU cost, run
   `python tests/coding_ui_fixture.py --port 8085` and submit `[scenario:coding]` tasks.
   Add `badgate`, `reviewfail`, `xss` or `connectors` to exercise those fixture paths.

### Next handoff

1. Review the local source and request a scoped source commit/PR; this documentation
   branch cannot deliver the implementation. Do not assume `coding-chat-cli` is remote.
2. Add tenant authentication/ownership and isolated per-user execution before public
   hosting, then durable task/result storage, cancellation, checkpoint-aware continuation
   and a remote authenticated terminal protocol. Do not use the current global config
   or workspace lock as multi-user security.
3. Add fair inference scheduling for ten users and their workers/reviewers without daily
   user quotas. Measure the chosen DeepSeek model, precision, context and four-H200
   topology before promising capacity. GPU spending needs separate host-level limits.
4. Separately authorize bounded live provider/model validation. Test account permissions,
   protected-branch/merge policies, partial writes, provider API limits and real workload
   quality; mocks do not establish production readiness.

## Coding product milestone 4 — authenticated single-tenant task access

The local `coding-chat-cli` implementation now requires operator-configured chat
authentication. Source is still uncommitted and unpublished; this documentation branch
contains none of the executable changes. This is an access-control milestone for one
trusted repository/tenant per process, not isolated execution for unrelated tenants.

- Added `app/access.py` and `app/access.example.json`. An external configuration selected
  by `AGENT_CHAT_AUTH_CONFIG` names one tenant, users, their credential environment-variable
  names and the exact public origin. Missing authentication configuration fails startup;
  missing/weak/duplicate tokens, unknown configuration fields and workspace-owned
  configuration are rejected. There is no anonymous/local bypass or proxy-header identity.
- HTTP clients authenticate with `Authorization: Bearer ...`; browser users sign in using
  an access-token form. Tokens are not accepted in query strings. The server stores token
  and session digests, not their plaintext, and does not insert credentials into task
  prompts, tool arguments or traces. Operators must generate independent high-entropy
  tokens; the minimum length check is not proof of entropy or password security.
- Browser sessions are opaque, HttpOnly, SameSite=Strict, host-only cookies, marked Secure
  for HTTPS. HTTPS is required except for explicitly configured loopback HTTP fixtures.
  Login and cookie-authenticated mutations require the exact configured Origin; invalid
  Authorization headers cannot fall back to an otherwise valid cookie. Responses use
  no-store. Token issuance, account onboarding and OAuth/SSO remain operator responsibilities.
- Each task stores the authenticated tenant/user identity. Only that principal can read
  its SSE stream or approve its exact pending prompt; other principals see the same 404
  as a missing run, even when they know its IDs. User-supplied owner/tenant fields cannot
  choose task ownership. Provider writes still require their existing explicit approval.
- Logout revokes that browser session, and open SSE streams recheck session validity before
  sending another batch. Expiration defaults to one hour and is operator-configurable
  between 60 seconds and one day. Up to eight active browser sessions per user are retained;
  older sessions are revoked. This is credential housekeeping, not a daily task/token quota.
  Logout does not cancel a running job or automatically deny every outstanding prompt;
  job cancellation and durable approval state remain future work.
- The UI shows the signed-in identity and sign-out control. Small-screen browser testing
  caught the sticky composer obscuring verification details after adding the identity row.
  The composer now stays in document flow; after restarting the fixture, the reply/checks/
  review were visible with no overlap or horizontal overflow and a cleared task input.

Focused authentication verification: **22/22 unittest methods passed**, covering config
boundaries, credentials, origins, cookies, expiration, session bounds, logout/replay,
unauthenticated rejection before model execution, owner assignment, cross-user streams
and pending approvals, live-stream revocation and real fixture coding without access
credentials in model requests/results/traces. The existing chat/coding HTTP suites also
passed with authenticated fixtures.

Final continuous Windows/Python 3.14.3 regression after the layout correction:

| Script | Passing checks/tests |
|---|---:|
| `test_access.py` | 22 |
| `test_app.py` | 34 |
| `test_code_cli.py` | 10 |
| `test_coding.py` | 13 |
| `test_coding_app.py` | 12 |
| `test_delivery.py` | 70 |
| `test_eval_cases.py` | 51 |
| `test_evals.py` | 7 |
| `test_harness.py` | 126 |
| `test_integrations.py` | 24 |
| **Total: all ten scripts exited 0** | **369/369** |

Internal-browser verification used only local model/provider fixtures: initial redirect
and invalid-token rejection, valid login with an HttpOnly cookie, approved connector write
and accepted implementation/check/review, sign-out with subsequent stream access denied
401, then another configured user denied access to the first user's stream/approval with
404. The final fixture restart invalidated previous sessions; signing in again and rerunning
accepted coding confirmed the corrected mobile layout. Its screenshot was visually reviewed
and the current-page console had no warnings/errors. Intentional unauthorized probes returned
401/404; those are expected access-control outcomes, not feature failures.

The existing Playwright/Chrome browser script was updated for mandatory login and its
now-ambiguous form selectors, with a reply/composer overlap assertion. It was not run in
this instance; manual in-app browser evidence is separate from the 369 offline checks.
No dependencies were installed, no live accounts or GPU were used, and main/hosted CI
counts or statuses were not changed by these local passes.

### Authentication prerequisite and next handoff

1. Copy `app/access.example.json` outside the editable repository. Choose one tenant and
   its trusted users, remove unused entries and set `origin` to the exact browser-facing
   scheme/host/port, without a trailing slash. Keep loopback HTTP local; public-facing
   transport requires separately configured TLS and correctly trusted reverse-proxy headers.
2. Generate separate random access tokens using `secrets.token_urlsafe(32)` or equivalent,
   and export them under the configured environment-variable names. Do not reuse model or
   provider keys, place tokens in the configuration, pass them as task text/URLs, or forward
   credential environment variables into project checks. Set `AGENT_CHAT_AUTH_CONFIG` to
   the external file before starting chat using the milestone 3 run order. The local coding
   CLI continues to use the operator's local workspace/config; it is not a remote client.
3. Treat users in one process as trusted collaborators on the same repository. Their
   files, harness globals, checks, model endpoint and provider credential scopes remain
   shared. HTTP task ownership is not file confidentiality, OS isolation, cross-process
   workspace locking or protection against hostile project code. Sessions and run events
   remain in memory; authentication does not make the current server safe for public
   multi-tenant hosting.
4. Next implementation milestone: isolated per-tenant execution with separate workspace,
   configuration and provider credentials, followed by durable tasks/results, cancellation
   and fair dispatch. Add remote terminal transport and measure the planned four-H200
   DeepSeek service only after those boundaries exist. No daily user quota was introduced.
5. Source review/commit/PR and live deployment remain separate authorization steps; the
   published progress branch alone does not deliver the implementation.

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
4. After runtime/skills PRs merge, rerun browser flows on that actual merged integration.
   Coding chat/terminal and manual browser validation are complete locally in milestone 3;
   full five-stage delivery/chat integration and hosted access remain separate work.
5. Separately authorize bounded live-model delivery/eval validation and confirm actual
   pod shutdown, preserving failures and assisted results as well as successes.
6. Enforce host/container isolation and deployment budgets. Workspace checks and approvals
   are not an OS sandbox; model-token budgets do not cap GPU rental spending.
7. Rebuild and review the design document after the implementation settles.
