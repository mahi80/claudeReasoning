# claudeReasoning

A small, readable agent harness in the style Claude itself runs in, built to work with
open-weight models (Gemma 4, Mistral Small 4, DeepSeek V4-Flash and V4.1-Flash) served by vLLM on
Runpod on-demand Pods. It comes with a chat UI, on-demand GPU start and stop, and a
design document that explains every part.

> **Status.** Local automated checks use mock model/Runpod endpoints. The current
> local fixes were separately revalidated on one B300 with DeepSeek V4-Flash and
> vLLM 0.34.0 on 27 November 2026, using an uncommitted snapshot based on `f00e4ea`.
> Decode CUDA graphs replaced eager execution: the original workflow passed 17/17
> checks with independent PASS in 63.9 seconds under the unchanged 600-second limit.
> Four selected cases at low/medium passed 8/8 under the original 90-second limits.
> Failed eager baselines are preserved. This is not a full 19-case benchmark or
> production-readiness evidence; see [`infra/runpod.md`](infra/runpod.md) for the
> tested configuration, safety checks and remaining deployment-specific limits.

## Progress and handoff — 28 November 2026

This is a dated coordination snapshot, not a claim that every tested change is on
`main`. The goal is a task executor with planning, scoped workers, lazily loaded skills,
approved MCP/tools, verification and code-gated delivery; proprietary-model parity is
not measured.

### Available on GitHub

| Location | Completed work | Status |
|---|---|---|
| `main` at `440c409` | PR #1: runtime/approval safety, scoped delegation, configured MCP and shared budgets | Merged |
| `main` at `440c409` | PR #2: five-stage delivery runner, guarded checks/commits/push and ADR gates | Merged |
| `main` at `440c409` | PR #3: Apache 2.0 project license | Merged |
| `main` at `440c409` | PR #4: 19th `make-tests-pass` eval, `--delivery` checks without git tools, isolated Python graders, pipeline/quality stage tests | Merged |
| `skills-import` at `18af506` | 33 compact instruction-only imports: document, coding, cloud and agent-regression guidance; eight originals preserved, 41 skills total | Published branch, not merged into `main` |
| `readme-progress` | This README handoff only | Documentation branch; runtime fixes below are not included |

The imported skills carry pinned provenance and license notices. Loader/provenance
checks passed; no third-party executables, hooks, assets or dependencies were installed.
Office generation, rendering and spreadsheet recalculation have not been validated.

### Completed locally, not published

The local `runtime-reliability` branch is based on merged `main` at `440c409`, with the
skills import and these uncommitted changes applied:

- **Pod lifecycle:** fail promptly on rejected starts, request idle shutdown even when
  `/health` is down, recheck activity under the lock, deduplicate accepted stops, restart
  after a stop request, retain restart state through rejected/failed starts, and keep
  the watchdog alive through transport failures. API
  acceptance is not proof of physical GPU shutdown; these checks used mocks only.
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

These runtime changes are **not fetchable from GitHub yet**. Do not assume a remote
`runtime-reliability` branch exists or that the documentation branch implements them.
The local integration applied cleanly and preserved both bots' mock-model scenarios;
there was no manual conflict resolution. Preserve both sets if a later integration
conflicts in the shared mock endpoint. Runtime commit, push and merge are still pending.

### Verification and next work

The merged-main baseline passed 288 non-browser checks on 28 November. The local
combined snapshot passed **374/374 offline checks** across ten scripts on Windows with
Python 3.14.3. This count is for the uncommitted integration, not `main` or this README
branch. Check counts include script assertions as well as unittest methods, not
benchmark tasks.

| Script in the local integration | Passing checks/tests |
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

To reproduce after the runtime patch is shared, activate an environment containing
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

No new live-model/GPU run or browser rerun was performed for these local changes. The
27 November B300 evidence above predates them and the delivery runner; it does not
validate the new delivery stages or the full 19-case benchmark.

Remaining work, in order:

1. Review and publish the local runtime patch on a separate branch, then integrate the
   published skills with explicit approval; do not overwrite either bot's worktree.
2. Add a CI driver for the offline suites; keep browser prerequisites/skips explicit.
3. Rerun browser coverage and connect delivery-stage execution/results to the chat UI.
4. Separately authorize a bounded live-model delivery/eval validation and confirm actual
   pod shutdown, preserving failures and assisted results as well as successes.
5. Enforce host/container isolation and deployment budgets. Current workspace checks and
   approvals are not an OS sandbox; model-token budgets do not cap GPU rental spending.
6. Rebuild and review the design document after the implementation settles.

## What is in here

| Path | What it holds |
|---|---|
| [`docs/agent-harness-open-models-runpod.docx`](docs/agent-harness-open-models-runpod.docx) | The design document: how the reference harness works, architecture, model options, Runpod sizing and cost, implementation guide, reliability, security, delivery plan, sources |
| [`harness/mini_harness.py`](harness/mini_harness.py) | The agent loop, tools, subagents, skills, plan, checkpoints, bounded context, effort levels and trace |
| [`harness/mcp_bridge.py`](harness/mcp_bridge.py) | MCP servers as harness tools (mcp SDK 2.x) |
| [`harness/pod_manager.py`](harness/pod_manager.py) | Start the Runpod pod on demand, wait for `/health`, stop it when idle |
| [`harness/run_evals.py`](harness/run_evals.py) | Replay a task file and report pass rate, steps, tokens and tool failures, one line per effort level |
| [`harness/smoke_test.py`](harness/smoke_test.py) | Proves an endpoint returns parsed tool calls and that the thinking switch works |
| [`harness/deliver.py`](harness/deliver.py) | Delivery stage runner: plan, platform, build, pipeline and quality stages, each judged by a gate written in code |
| [`harness/delivery_tools.py`](harness/delivery_tools.py) | Guarded delivery tools: pre-approved checks, local commits, one approved push that opens the pull request |
| [`harness/checks/adr_lint.py`](harness/checks/adr_lint.py) | Lint for architecture decision records: file names, template, index |
| [`skills/`](skills) | Skills the model loads on demand, including the seven delivery skills |
| [`app/server.py`](app/server.py) | HTMX chat UI on FastAPI: live progress, plan checklist, approvals, effort picker |
| [`infra/runpod.md`](infra/runpod.md) | Pod template, serve commands per model, prices and monthly cost |
| [`tests/`](tests) | Mock model endpoint, mock Runpod API and six test scripts |

## How it works

![The loop and the four things it can reach](docs/img/fig_loop.png)

There is no graph framework. One loop does everything:

1. The model gets the rules, a list of tools with descriptions, and the task.
2. It replies with text or with tool calls.
3. The harness runs the calls and appends the results.
4. Repeat until the model answers in plain text.

**How it decides which tools, skills and subagents to use.** Nothing is hard-coded. The
model matches each sub-task against the tool descriptions, loads a skill only when its
one-line summary fits, and delegates to a worker agent when a chunk is independent or
heavy. Each worker gets an explicit minimal tool list from its parent's capabilities;
it cannot gain tools, spawn another worker or change the main plan. Workers with
`load_skill` also see the skill index. Configured MCP tools participate in the same
routing and approval policy. The model re-decides after every result; descriptions and
`orchestrator_system()` are the routing logic.

**Long-running tasks** use the same rule, with four supports: a plan the model keeps
updating (`update_plan`, pinned into every prompt), skills loaded late, subagents that
keep the main context small, and a checkpoint after every step so a stopped run can
resume.

**Context is checked before every model request**, including summary requests. A
conservative serialized-JSON byte estimate includes messages and tool schemas, with
space reserved for the reply and 4,096 tokens of template overhead. This is not exact
model tokenization. Older history and oversized tool results are compacted without
orphaning tool replies; an oversized pinned task, plan or schema fails clearly instead
of silently truncating instructions. Extra request fields cannot override messages,
tools or reply limits.

**Open models call tools less reliably**, so the harness feeds every failure back as
text the model can act on: bad JSON, unknown tools, repeated calls, denied actions.

## Effort levels

Claude takes an effort level with each request (low, medium, high, xhigh, max) and was
trained to follow it. An open model was not, so the harness builds the same dial from
parts it controls. Pick a level per task with `--effort`, the `effort=` argument of
`run_agent`, or the picker in the chat UI. Medium is the default.

| Level | Model's own thinking | Steps | Reply tokens | Workers | Self-check | Review correction rounds |
|---|---|---|---|---|---|---|
| `low` | Off, and no think tool | 8 | 4,096 | None | No | 0 |
| `medium` | First step, and the step after a failed tool call | 20 | 4,096 | 2 | No | 0 |
| `high` | Every call | 40 | 8,192 | 4 | Yes | 0 |
| `xhigh` | Every call | 80 | 8,192 | 6 | Yes | 1 |
| `max` | Every call, in the model's deepest mode | 150 | 16,384 | 8 | Yes | 2 |

What sits behind the columns, all in `harness/mini_harness.py`:

- **The model's own thinking** uses `LLM_THINKING`, a JSON map of request fields for
  `off`, `on` and optionally `max` and `brief`. The default `LLM_THINKING_SCOPE=step`
  switches medium effort on its first step and after failed tools. Use `task` for
  conversation-level thinking: medium then uses `brief` throughout, or `on` if no
  `brief` is defined; low stays off and high stays on. The fields differ per model;
  [`infra/runpod.md`](infra/runpod.md) has them for each supported preset.
- **One line of guidance per level** is added to every system prompt (`GUIDANCE`).
- **A `think` tool** gives the model a place to reason between tool calls.
- **Self-check** (high and above): before an answer is accepted, the model checks it
  against the task and replies exactly CONFIRMED or gives the full corrected answer.
- **Independent review** (xhigh, max): a fresh-context agent with read-only tools must
  return PASS alone on its first non-empty line (case-insensitive). Any other verdict,
  including an empty or unfinished review, rejects the answer. Xhigh allows one
  correction round and max allows two; every corrected answer is reviewed again.
  Exhausting the budget returns an explicit stopped result, not an unreviewed draft.
  The reviewer receives runtime-observed tool arguments/results, including loaded skills
  and worker calls, alongside the task and answer, but not the coordinator's reasoning.
  It still inspects workspace artifacts; clipped evidence is explicitly incomplete.
  Checkpoints preserve these observations across compaction and manual resume, and the
  trace records reviewer verdicts for diagnosis.
- **Escalation** (`--escalate`, `run_escalating`): start cheap and climb a level when a
  run stalls or a check you supply rejects the answer.

Choose a level from data, not by feel:

```bash
AGENT_WORKSPACE=/tmp/eval-workspace python harness/run_evals.py evals/tasks.agent.jsonl 3 \
    --effort low medium high
```

The last lines of the output give pass rate, steps and output tokens per level.
`evals/tasks.agent.jsonl` contains 19 cases; `evals/tasks.example.jsonl` is the smaller
example. Add `--delivery evals/delivery.evals.json` to give the agent the `run_checks`
tool with a `tests` check, which the last case, `make-tests-pass`, is written for: it
measures whether the model can make a failing test suite pass when it can run the tests
itself, the skill the delivery stages depend on. `--shard 0/2` and `--shard 1/2` split cases over two processes; use different
workspace, trace and checkpoint paths for each process. This runner reuses the workspace
for each case, so only the last case's workspace remains; retain the report and trace for
previous attempts. Failed or stopped runs always fail grading, even if their files
satisfy an artifact-only check.

None of this adds reasoning ability the model does not have. It helps a model use what
it has: fewer slips, fewer early exits, a second look. If high effort still fails your
evals, the next move is a stronger model, not a higher level.

## Quick start

Needs Python 3.11 or newer. The local checks were run on Windows with Python 3.14.
If your system Python is older, `uv` adds a newer one beside it:

```bash
pip install uv && uv python install 3.13
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

Otherwise:

```bash
pip install -r requirements.txt

python tests/test_harness.py      # 126 checks: tools, context, review evidence, MCP config, workers and budgets
python tests/test_evals.py        # 7 checks: grading, failure scoring, effort comparison and --delivery
python tests/test_eval_cases.py   # 51 checks: task graders, reference solutions and near-misses
python tests/test_app.py          # 34 checks: chat UI, pod manager, approvals and budget deadlines
python tests/test_delivery.py     # 70 checks: delivery config, guarded tools, ADR lint, gate and all five stages (needs git)
python tests/test_ui_browser.py   # 22 checks in Chrome, including the complete skill/worker/MCP flow
```

The 288 non-browser checks passed locally on 28 November 2026 (Windows, Python 3.14);
the 22 browser checks last passed on 27 November 2026. Browser checks additionally need
`pip install playwright` and installed Chrome or Chromium. Missing prerequisites produce
a skip, not verification. If HTTPX rejects an IPv6 entry in your proxy exclusions, run
local checks with `NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost` for that
process only.

### Run it against your own model

1. Serve a model. [`infra/runpod.md`](infra/runpod.md) has the pod template and the
   `vllm serve` command for each model.
2. Check the endpoint, then give the agent a task:

```bash
export LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1
export LLM_API_KEY=<your vLLM key>
export LLM_MODEL=agent-model

# Gemma 4: how to switch thinking, and the server's --max-model-len
export LLM_THINKING='{"off": {"chat_template_kwargs": {"enable_thinking": false}},
                      "on":  {"chat_template_kwargs": {"enable_thinking": true}}}'
export LLM_KEEP_REASONING=1
export LLM_CONTEXT_WINDOW=32768

python harness/smoke_test.py
python harness/mini_harness.py "Create notes/todo.md with three items and read it back"
python harness/mini_harness.py --effort high "Compare the two files in notes/ and list the differences"
python harness/mini_harness.py --resume "Create notes/todo.md with three items and read it back"
```

`--effort` takes `low`, `medium` (the default), `high`, `xhigh` or `max`. `--resume`
continues the same task from its last checkpoint, for example after the step limit or a
stopped pod. `--escalate` starts at the given level and climbs one level each time a run
stalls. With `LLM_THINKING` set, the smoke test also fails if a fragment does not switch
the model's thinking.

3. Or use the chat UI:

```bash
export RUNPOD_POD_ID=<pod id>          # optional: start on demand, stop when idle
export RUNPOD_API_KEY=<runpod key>
uvicorn server:app --app-dir app --host 127.0.0.1 --port 8080
```

### Configure MCP capabilities

MCP is opt-in: only an operator-controlled JSON configuration can launch servers or
connect them. The model cannot install a server or choose an arbitrary endpoint.
For the bundled arithmetic test server, a configuration contains:

```json
{
  "servers": {
    "demo": {
      "command": "python",
      "args": ["tests/demo_mcp_server.py"],
      "tools": ["add"]
    }
  }
}
```

Set `AGENT_MCP_CONFIG` to that file's absolute path and launch from the repository
root with the virtual environment activated. Both the CLI and chat UI connect the
configured servers and expose only allowlisted tools, named `demo__add` in this example.
All MCP calls still require approval; use the chat UI's Approve/Deny buttons. Unattended
CLI runs deny them unless explicitly configured with `AGENT_AUTO_APPROVE` in a sandbox.

A remote definition uses `url` and `tools` instead of `command` and `args`. For stdio
credentials, an optional `env` list names environment variables to pass through;
values stay in the environment, not the configuration or model prompt. Do not point
this configuration at untrusted executables. Connections close on normal CLI/UI shutdown.

### Shared execution budgets

The coordinator, workers, reviewers, compaction and effort escalation share one
execution budget. Before a model call starts, its conservative prompt estimate and
reply allowance are reserved atomically, so parallel workers cannot spend the same
remaining allowance. The reply cap shrinks to the remaining token/cost allowance
instead of rejecting a call solely because the full effort-level reply cap will not fit.
If the prompt plus even one reply token cannot fit, the run stops. Prompt estimation
remains conservative, not exact model tokenization. Complete usage releases unused
reservations; missing
usage and failed calls retain conservative accounting. Exhaustion returns a stopped
result, and escalation cannot reset the budget.

The defaults are 900 seconds and 100,000 total model tokens; `0` disables either cap.
`AGENT_MAX_COST_USD` optionally limits estimated model-token cost and requires positive
`LLM_INPUT_USD_PER_MILLION` and `LLM_OUTPUT_USD_PER_MILLION` prices for your endpoint.
Budget usage and stops are recorded in the trace. Model calls, shell execution, MCP
waits and approval waits use the remaining deadline; cancellation of in-flight remote
actions is best-effort and cannot undo their effects.

These limits cover agent execution, not preceding GPU/MCP startup or Runpod rental.
They are not a billing guarantee or an OS sandbox. Separate chat requests and manual
checkpoint resumes start fresh budgets; effort escalation within one invocation does not.

## Delivery stages: from a plan to a pull request

[`harness/deliver.py`](harness/deliver.py) runs the agent as the coder inside a
human-gated delivery pipeline. Each stage is one escalating run. A gate written in code,
not the model's own judgement, accepts or rejects the result, a person reviews between
stages and on the pull request, and GitHub Actions and SonarQube run on GitHub where
people read them: the agent never sees CI.

| Stage | The agent produces | The gate requires |
|---|---|---|
| `plan` | `docs/plan/features.md` from `docs/plan.md` | at least one feature marked "this run" |
| `platform` | `docs/adr/0001-platform.md` (Proposed) and the ADR index | the ADR lint, a record added or changed since the stage started |
| `build` | code and tests for the "this run" features, committed | the configured checks, the ADR lint, a clean tree ahead of the base branch |
| `pipeline` | `.github/workflows/ci.yml` and its ADR, committed | `actionlint` if configured, the ADR lint, the git state |
| `quality` | `sonar-project.properties`, the quality-gate job and its ADR, committed | the checks (`tests`, `sonar` if configured), the ADR lint, the git state |

Setup, once per target repository, on a disposable host that is not the GPU pod:

```bash
git clone --separate-git-dir=/srv/delivery/target.git https://github.com/org/repo.git /srv/delivery/repo
cp harness/delivery.example.json /srv/delivery/config.json      # edit checks, git, remote
export AGENT_WORKSPACE=/srv/delivery/repo AGENT_DELIVERY_CONFIG=/srv/delivery/config.json
export AGENT_MAX_SECONDS=3600 AGENT_MAX_TOTAL_TOKENS=400000
python harness/deliver.py --stage plan               # then read docs/plan/features.md
python harness/deliver.py --stage platform           # then accept or edit docs/adr/0001-platform.md
python harness/deliver.py --stage build --branch feature/first
GH_TOKEN=<fine-grained token: contents and pull requests on this one repository> \
    python harness/deliver.py --push-only --branch feature/first
```

The harness checkout, its interpreter and the config stay outside the workspace. The
config pins the `checks` the model may run through the `run_checks` tool (argv lists,
timeouts, the names of environment variables each one may see; every such name must be
exported before a stage whose gate runs that check, so `sonar` needs `SONAR_TOKEN` and
`SONAR_HOST_URL`, and `actionlint` and `sonar-scanner` must be installed on the harness
host), the `gate` list, and a `git` block: the separate git dir, the remote, the base
branch, protected branch patterns, the commit author, the name of the token variable
and `config`, git settings the operator needs (a proxy, say), which are passed on the
command line. `run_checks` and `git_commit` need no approval click: the operator
pre-approved the argv, and the commit is local, on a feature branch, with hooks, system
and user configuration disabled and `.agent/` and check reports left out. Before every
git command the harness scans the configuration git would read and refuses any file
setting that could redirect a push or run a program (URL rewrites, proxies, hooks,
filters, includes, remotes named by a URL, push URLs). `git_push_pr` is the only tool
that asks for approval; it refuses a rewritten URL, the token reaches git only through
[`harness/git_credential.py`](harness/git_credential.py), which answers for the
configured host over https alone, and the pull request is opened through the GitHub
API. Run the push as its own command (`--push-only`) so the token is never in the
environment while the agent's checks execute model-written code. A rejected gate writes
`.agent/gate-report.md` and the next effort level starts from an empty transcript and
that report. A stage that must record a decision (`adr.require_changed`) is judged on
the records the agent added or changed since the stage started, in its own commits or
still uncommitted; the start is remembered across re-runs of a rejected stage. Exit codes:
0 accepted or pushed and the pull request open, 1 rejected, 2 stopped at a limit, 3 the
run failed or the arguments were wrong, 4 not pushed (not approved, branch not ready,
push or pull request failed); `--result FILE` writes the outcome as JSON. The plain CLI gained the same `--run-id` and `--result`
options and exit codes 0, 2 and 3. Console approvals need an interactive terminal;
without one every approval is refused and the model is told nobody can approve.

Seven skills carry the guidance: `delivery-workflow`, `feature-planning`,
`cloud-choice`, `adr`, `github-actions`, `sonarqube` and `coding-conventions`.
[`harness/checks/adr_lint.py`](harness/checks/adr_lint.py) enforces the ADR template,
numbering and index, in the gate and as the `adr` check the model can run itself.

What to expect: one small feature per run (two to four files of about 150 lines each)
at the 32K context; serve a 65,536 window and raise `AGENT_CONTEXT_BUDGET` for high
effort and above. Measure before you rely on it: run the eval set with
`--delivery evals/delivery.evals.json` (see Effort levels) and look at the pass rate of
`make-tests-pass` per effort level; a model that cannot make one failing test pass with
the test runner in hand will not complete a build stage either. The cloud choice is a proposal from the plan's constraints, not from
prices or accounts, and deployment belongs to the CI job with OIDC and a protected
environment, never to the agent. The model's capability on real repositories is
unmeasured: the evals are small single-folder tasks, so run a dry run against a
scratch repository first.

## From chat message to GPU and back

![Chat UI: GPU start, plan checklist and approval prompt](docs/img/ui-flow.png)

*The reference UI in headless Chrome, running against the mock endpoints.*

| # | Who acts | What happens | What the user sees |
|---|---|---|---|
| 1 | Browser (HTMX) | The form posts the task to `/chat` | Their message |
| 2 | Backend (FastAPI) | Creates a run and opens a server-sent event stream | "Queued" |
| 3 | Pod manager | Checks `/health`; if down, calls Runpod's start endpoint and polls | "Starting the GPU pod", then "Model server is ready" |
| 4 | Harness loop | The model picks tools, the harness runs them, the model decides the next step | The agent's checklist and a status line per step |
| 5 | Approval gate | Shell commands outside the checked read-only subset and all MCP calls pause the run; approvals are command-specific | Approve and Deny buttons, one request at a time |
| 6 | Harness | The model answers in plain text | The answer |
| 7 | Idle watchdog | No runs for the idle period: calls Runpod's stop endpoint | Nothing; the next request cold-starts |

Starting and stopping the GPU is ordinary code, not a model decision: the model runs on
that GPU, so it cannot decide its own start.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:8000/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | `EMPTY` | Endpoint key |
| `LLM_MODEL` | `agent-model` | Served model name |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature; see the model's recipe |
| `LLM_EXTRA_BODY` | `{}` | Extra request fields sent on every call, as JSON (for example `top_p`) |
| `LLM_THINKING` | `{}` | Request fields for `off`, `on` and optionally `max` and `brief` |
| `LLM_THINKING_SCOPE` | `step` | `task` keeps medium thinking on throughout, using `brief` if present |
| `LLM_KEEP_REASONING` | `0` | `1` sends the model's reasoning back with each tool-call turn (Gemma 4, DeepSeek V4) |
| `LLM_CONTEXT_WINDOW` | `32768` | Match the server's `--max-model-len`; requests reserve reply and template space |
| `AGENT_WORKSPACE` | `workspace` | File-tool boundary and shell working directory; approved shell commands are not jailed |
| `AGENT_SKILLS` | `skills` | Folder of `<name>/SKILL.md` |
| `AGENT_TRACE` | `trace.jsonl` | One JSON line per model call and tool call |
| `AGENT_CHECKPOINTS` | `checkpoints` | Saved state for `--resume` |
| `AGENT_MAX_STEPS` | `0` | Lowers the step cap for every effort level; `0` keeps each level's own cap |
| `AGENT_CONTEXT_BUDGET` | `24000` | Soft message-size estimate for compaction; the context-window preflight also includes schemas |
| `AGENT_MCP_CONFIG` | unset | Operator-controlled JSON file of approved servers and tool allowlists |
| `AGENT_DELIVERY_CONFIG` | unset | Operator-controlled JSON file of pre-approved checks, git dir, remote and base branch for `deliver.py` |
| `AGENT_MAX_SECONDS` | `900` | Shared agent-execution deadline; `0` disables it |
| `AGENT_MAX_TOTAL_TOKENS` | `100000` | Shared model-token allowance, including workers and summaries; `0` disables it |
| `AGENT_MAX_COST_USD` | `0` | Optional estimated model-token cost limit, not GPU rental |
| `LLM_INPUT_USD_PER_MILLION`, `LLM_OUTPUT_USD_PER_MILLION` | `0` | Endpoint token prices; both must be positive when a cost cap is set |
| `AGENT_AUTO_APPROVE` | `0` | `1` skips approvals; only for a throwaway sandbox |
| `RUNPOD_POD_ID`, `RUNPOD_API_KEY` | unset | Set both to let the pod manager start and stop the pod |
| `LLM_HEALTH_URL` | the pod's proxy `/health` | Readiness check |
| `POD_IDLE_SECONDS` | `900` | Stop the pod after this much quiet |
| `POD_START_TIMEOUT` | `1500` | Give up on a start after this many seconds |
| `APPROVAL_TIMEOUT` | `300` | An unanswered approval counts as a refusal |

## Runpod on-demand cost at a glance

Secure Cloud rates read on 27 November 2026. Month totals include a weights volume.

| Model | Pod | Per hour | Month at 176 h | Month always on |
|---|---|---|---|---|
| Gemma 4 26B-A4B | 1x A100 PCIe 80 GB | $2.09 | $378 | $1,536 |
| Gemma 4 26B-A4B | 1x H100 PCIe 80 GB | $2.89 | $519 | $2,120 |
| Gemma 4 31B | 1x H200 | $5.29 | $942 | $3,872 |
| Mistral Small 4 (FP8) | 2x H200 | $10.58 | $1,880 | $7,741 |
| DeepSeek V4-Flash (FP8) | 8x H200 | $42.32 | $7,476 | $30,922 |
| DeepSeek V4.1-Flash (FP8) | 4x H200 | $21.16 | $3,773 | $15,496 |
| DeepSeek V4.1-Flash (FP8) | 2x B200, one session at a time | $15.98 | $2,861 | $11,714 |

V4.1-Flash is the newer DeepSeek release. It rents for about half of V4-Flash's
eight-GPU recipe default, but it is the hardest of these to operate: a 511 GB checkpoint,
part of the model held in system memory, and a first load the recipe allows an hour for.

All thirteen configurations, the price table and the caveats are in
[`infra/runpod.md`](infra/runpod.md). Runpod changes prices often: edit `RATE` in
[`infra/costs.py`](infra/costs.py) and run it to recalculate.

### Disposable GPU validation

`infra/pod_test.sh` runs on the selected Linux GPU pod, not on your desktop. It supports
`gemma4`, `deepseek-v4` (one B300) and `deepseek-v41` (four H200), with `setup`, `serve`,
`smoke` and `evals` steps. It binds vLLM to localhost. See
[`infra/runpod.md`](infra/runpod.md) for settings, sharding, saved outputs and the
32K context used in the actual DeepSeek experiment. The script installs the then-current
vLLM; pin the tested image/model revision separately for reproducibility. It does not
stop the GPU or cap rental spending: export results and stop the pod yourself.

## Limits you should know about

- **Live coverage remains limited.** The graph-enabled B300 revalidation passed the
  scoped skill/worker/MCP workflow with strict independent review, plus four selected
  cases at low/medium. Failed eager baselines are preserved; this is not the full
  19-case benchmark. Run the smoke test and your own evals before deployment.
- **Most serving/thinking presets remain untested live.** Only the DeepSeek V4-Flash
  0731 configuration above had live protocol/thinking probes. Gemma, Mistral, V4.1,
  larger contexts and max-thinking configurations still need deployment-specific tests.
- **Higher effort costs more.** High and above think on every call and add at least one
  more model call per task; a review is a second agent run.
- **Workspace file writes are permitted without approval.** `write_file`, `edit_file`
  and plan updates may change files inside the workspace. MCP tools require approval.
  Automatic shell reads use checked literal workspace paths, a limited set of flags,
  and no shell expansion; other commands require approval. Recursive shell reads are
  not automatically approved because they can follow links outside the workspace.
- **Delivery checks and commits run without a click.** With a delivery config,
  `run_checks` runs the operator's pinned commands and `git_commit` commits locally, so
  pytest or npm executes code the model wrote on the harness host, as the same user as
  the harness. The environment allow-list and the git hardening are hygiene, not a
  boundary: keep that host disposable or run the checks under another user or in a
  container, scope the push token to one repository and export it only for
  `--push-only`, and never combine delivery with `AGENT_AUTO_APPROVE=1`.
- **The approval layer is not a sandbox.** Approved shell commands can access the host
  outside the workspace. Runpod pods cannot run nested containers, so put the agent on
  a separate disposable pod or VM that holds no credentials.
- **The chat UI has no login** and all runs share one workspace. Keep it on localhost or
  put it behind your own authentication, and give each session its own sandbox.
- **vLLM's API key does not protect every endpoint** (only `/v1`, `/v2` and `/inference`).
  For sensitive data, do not expose port 8000 through the public proxy.
- **Model cards overstate tool-calling reliability.** Choose a model from your own eval
  results. Section 4 of the document has the evidence.

## Rebuilding the document

```bash
npm install docx
bash docs/build/make.sh
```

The code listings in the document are cut from the source files by
`docs/build/excerpts.py`, so the document cannot drift from the code.

## Versions and third-party files

Tested with Python 3.13, openai 3.60.0, mcp 2.3.0, fastapi 0.165.0, uvicorn 0.54.0.
`app/static/` holds unmodified copies of htmx 2.0.10 and its SSE extension 2.2.4, both
under the Zero-Clause BSD licence; see
[`app/static/THIRD_PARTY.md`](app/static/THIRD_PARTY.md).

## License

Apache License 2.0; see [`LICENSE`](LICENSE). Third-party notices are in
[`NOTICE`](NOTICE) and, for the vendored htmx files, in
[`app/static/THIRD_PARTY.md`](app/static/THIRD_PARTY.md).
