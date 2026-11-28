"""deliver.py - run one delivery stage through the agent, then judge it with a gate.

    AGENT_DELIVERY_CONFIG=/srv/delivery/config.json AGENT_WORKSPACE=/srv/delivery/repo \\
        python harness/deliver.py --stage build --branch feature/login
    GH_TOKEN=... python harness/deliver.py --push-only --branch feature/login

The target repository is cloned into the workspace with its git dir outside it
(git clone --separate-git-dir); the config names that git dir, the checks the agent may
run and the remote (harness/delivery.example.json). Stages, in order:

    plan      read docs/plan.md, write docs/plan/features.md (a person reviews it)
    platform  propose the cloud or platform as docs/adr/0001-platform.md (a person accepts it)
    build     implement the features marked "this run", checks passing, committed
    pipeline  add .github/workflows/ci.yml and its ADR, committed
    quality   add the SonarQube project file, the quality-gate job and its ADR, committed

Each stage is one escalating agent run. The gate is code, not the model: the stage's
files, the git state, the configured check commands and the ADR lint. A rejected result
is written to .agent/gate-report.md and the next effort level starts from it. Approvals
(run_shell beyond read-only commands, the push) are asked on this console when there is
one; without a console they are refused and the model is told so. --push-only pushes an
accepted branch and opens the pull request in a process of its own, so the token is
exported for that command alone and never while the agent's checks run.

Exit codes: 0 the gate accepted the result (or the push succeeded and the pull request
is open), 1 the gate rejected it, 2 the run stopped at a limit before the gate could
pass, 3 the run itself failed or the arguments were wrong, 4 not pushed: not approved,
the branch not ready, or the push or the pull request failed.
"""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE / "checks"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import adr_lint  # noqa: E402
import delivery_tools as dt  # noqa: E402
import mini_harness as h  # noqa: E402

APPROVAL_TIMEOUT = float(os.environ.get("APPROVAL_TIMEOUT", "300"))
REPORT, PR_FILE, PR_BODY = ".agent/gate-report.md", ".agent/pr.md", ".agent/pr-body.md"
PLAN, FEATURES = "docs/plan.md", "docs/plan/features.md"
LINT = HERE / "checks" / "adr_lint.py"
COMMIT_STAGES = ("build", "pipeline", "quality")
EXIT = {"accepted": 0, "pushed": 0, "rejected": 1, "stopped": 2, "failed": 3, "unpushed": 4}
READ = ("read_file", "list_dir", "load_skill", "find_skills", "update_plan", "think")
WRITE = READ + ("write_file", "edit_file")
BUILD = WRITE + ("run_shell", "run_checks", "git_commit", "spawn_agent")
TOOLS = {"plan": WRITE, "platform": WRITE + ("run_checks",), "build": BUILD,
         "pipeline": BUILD, "quality": BUILD}
RULES = """Delivery rules:
- Tests, linters and other checks run only through run_checks, never through run_shell.
- Never run git, gh, pip or npm through run_shell. Commit with git_commit; the operator pushes.
- Do not change docs/plan.md or the operator's configuration. Under .agent/ write only
  .agent/pr.md; update_plan keeps your checklist there for you.
- Keep every file you write under about 150 lines; split larger ones.
- Record each design decision as an ADR (load the adr skill); the gate lints them."""


@dataclass(frozen=True)
class Context:
    config: dt.Config
    stage: str
    branch: str
    plan: str
    features: str
    run_id: str
    note: str = ""
    start: str | None = None           # the commit the stage started from, for the ADR rule


# ---------------------------------------------------------------- the stage tasks
def task_for(ctx: Context) -> str:
    config, adr = ctx.config, ctx.config.adr_dir
    names = ", ".join(sorted(config.checks)) or "none"
    gate = ", ".join(config.checks_for(ctx.stage)) or "no configured checks"
    base = config.git.base if config.git else "the base branch"
    plan_dir = Path(ctx.plan).with_suffix("").as_posix()
    report = f"If {REPORT} exists, read it first: it says why the previous attempt was rejected."
    finish = (f"Write {PR_FILE}: first line the pull request title, then the body (what changed, "
              f"how it was tested, open items). Commit everything with git_commit(branch="
              f'"{ctx.branch}", message=...), then finish with a short summary.')
    texts = {
        "plan": f"""Delivery stage: plan. Decide which features to develop from the plan.
1. Load the skill feature-planning and follow it. {report}
2. Read the plan at {ctx.plan}. If the folder {plan_dir}/ exists, read every file in it too, and docs/constraints.md if it exists.
3. Write {ctx.features}: numbered features, each with its outcome, its acceptance check (one of the configured checks: {names}), size, dependencies and the marker "(this run)" or "(later)" in its heading. Mark "(this run)" only what fits one branch of a few small files.
4. Finish with the features chosen for this run and why.
Do not change the plan itself.""",
        "platform": f"""Delivery stage: platform. Propose the cloud or platform for this plan.
1. Load the skills cloud-choice and adr and follow them. {report}
2. Read {ctx.features}, docs/constraints.md if it exists, and the plan at {ctx.plan}.
3. Write {adr}/0001-platform.md with Status: Proposed: the platform, the service mapping, the deployment shape and the section "Assumptions to confirm". Write or update {adr}/README.md, the index.
4. Run run_checks with name "adr" and fix every problem it reports.
5. Finish by stating the proposed platform and the assumptions a person must confirm.
Nothing is deployed in this stage and no cloud credential exists here.""",
        "build": f"""Delivery stage: build. Implement the features marked "(this run)" in {ctx.features} on branch {ctx.branch}.
1. Load the skill delivery-workflow and follow it. {report}
2. Read {ctx.features} and {adr}/README.md if it exists. Read a file before you change it.
3. Implement one feature at a time, with tests. Keep each file under about 150 lines.
4. After each change run the checks with run_checks until they pass. The gate runs: {gate}.
5. Record any design decision (framework, data store, deviation from the plan) as an ADR.
6. {finish}
The gate rejects the run when a check fails, when a required ADR is missing, or when the branch has uncommitted changes or no commit ahead of {base}.""",
        "pipeline": f"""Delivery stage: pipeline. Add the GitHub Actions pipeline on branch {ctx.branch}.
1. Load the skills delivery-workflow, github-actions and adr and follow them. {report}
2. Read {ctx.features}, {adr}/0001-platform.md and any file under .github/workflows/. Find this repository's test and lint commands (README, pyproject.toml, package.json or similar).
3. Write .github/workflows/ci.yml from the skill's skeleton: test and lint jobs on every pull request, the quality job, and a deploy job that runs only from {base} and names its secrets without values.
4. Write an ADR for the pipeline design and update {adr}/README.md. Run the configured checks with run_checks: {gate}.
5. {finish}""",
        "quality": f"""Delivery stage: quality. Add the SonarQube quality gate on branch {ctx.branch}.
1. Load the skills delivery-workflow, sonarqube and adr and follow them. {report}
2. Read .github/workflows/ci.yml, {ctx.features} and {adr}/README.md.
3. Write sonar-project.properties (project key, sources, tests, exclusions, coverage report path) and make the CI test step produce that coverage report.
4. Add or adjust the sonar job in ci.yml so it waits for the quality gate and fails when the gate is red; name SONAR_TOKEN and SONAR_HOST_URL as secrets, never their values.
5. Write an ADR recording the quality thresholds and update {adr}/README.md. Run the configured checks with run_checks: {gate}.
6. {finish}""",
    }
    return texts[ctx.stage] + (f"\n\n{ctx.note}" if ctx.note else "")


# ---------------------------------------------------------------- the gate
@dataclass
class Item:
    name: str
    ok: bool
    detail: str = ""
    exit: int | None = None
    seconds: float = 0.0


def tail(text: str, limit: int = 3000) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def workspace_file(path: str) -> str | None:
    try:
        p = h.inside_workspace(path)
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    except PermissionError:
        return None


class Progress:
    """Trace events as one-line console status; counts the main agent's runs."""

    def __init__(self) -> None:
        self.efforts: list[str] = []
        self.runs = 0

    def __call__(self, record: dict) -> None:
        event = record["event"]
        if event == "run":
            self.runs += 1
            self.efforts.append(record["effort"])
            say(f"-- effort {record['effort']}" + (" (resumed)" if record.get("resume") else ""))
        elif event == "model" and record.get("tool_calls"):
            say(f"   {record['agent']} step {record['step']}: {', '.join(record['tool_calls'])}")
        elif event == "gate":
            verdicts = ", ".join(f"{i['name']} {'ok' if i['ok'] else 'FAIL'}" for i in record["items"])
            say(f"-- gate: {'passed' if record['passed'] else 'rejected'} ({verdicts})")
        elif event == "escalate":
            say(f"-- escalating after {record['after']}")
        elif event == "budget_limit":
            say(f"-- stopped: {record['reason']}")


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


class Gate:
    """Deterministic acceptance for one stage. Callable, so run_escalating uses it as accept.

    The git state is read before the checks run, because checks may write reports into
    the tree. It never calls time_left: it runs inside the shared run deadline, and a gate
    that raised BudgetExceeded would end the stage with a traceback instead of a report.
    """

    def __init__(self, ctx: Context, progress: Progress) -> None:
        self.ctx, self.progress, self.attempt = ctx, progress, 0
        self.passed: bool | None = None
        self.items: list[Item] = []
        self.judged_run = -1               # which main-agent run the last evaluation judged

    def __call__(self, answer: str) -> bool:
        return self.evaluate(answer)

    def evaluate(self, answer: str) -> bool:
        self.attempt += 1
        items = self.stage_items() + self.git_items()
        before = self.tree()
        items += self.check_items()
        items += self.generated_items(before) + self.adr_items()
        self.items, self.passed, self.judged_run = items, all(i.ok for i in items), self.progress.runs
        write_report(self.ctx, self.attempt, items, self.passed)
        h.trace("gate", stage=self.ctx.stage, attempt=self.attempt, passed=self.passed,
                items=[{"name": i.name, "ok": i.ok, "exit": i.exit} for i in items])
        return self.passed

    def stage_items(self) -> list[Item]:
        ctx, stage = self.ctx, self.ctx.stage
        if stage == "plan":
            text = workspace_file(ctx.features) or ""
            chosen = [line for line in text.splitlines()
                      if line.lstrip().startswith("#") and "(this run)" in line.lower()]
            return [Item("features", bool(chosen), f"{len(chosen)} marked for this run" if chosen else
                         f'{ctx.features} must exist with at least one feature heading marked "(this run)"')]
        if stage == "platform":
            path = f"{ctx.config.adr_dir}/0001-platform.md"
            lines = (workspace_file(path) or "").splitlines()
            ok = any(adr_lint.STATUS.fullmatch(line) and ("Proposed" in line or "Accepted" in line)
                     for line in lines)
            return [Item("platform-adr", ok, "" if ok else f"{path} must exist with Status: Proposed")]
        if stage == "pipeline":
            text = workspace_file(".github/workflows/ci.yml") or ""
            ok = "jobs:" in text and ("on:" in text or '"on":' in text)
            return [Item("ci-workflow", ok, "" if ok else ".github/workflows/ci.yml must define on: and jobs:")]
        if stage == "quality":
            text = workspace_file("sonar-project.properties") or ""
            ok = "sonar.projectKey=" in text
            return [Item("sonar-project", ok, "" if ok else "sonar-project.properties must set sonar.projectKey")]
        return []

    def git_items(self) -> list[Item]:
        ctx = self.ctx
        if not ctx.config.git or ctx.stage not in COMMIT_STAGES:
            return []
        problems = dt.git_problems(ctx.config, ctx.branch)
        return [Item("git", not problems, "\n".join(problems))]

    def tree(self) -> set[str] | None:
        """Paths that differ from HEAD, for the stages that commit and have checks to run."""
        ctx = self.ctx
        if not ctx.config.git or ctx.stage not in COMMIT_STAGES or not ctx.config.checks_for(ctx.stage):
            return None
        try:
            status = dt.tree_status(ctx.config)
        except dt.UnsafeConfig:
            return None
        return None if status is None else set(status)

    def check_items(self) -> list[Item]:
        config, items = self.ctx.config, []
        for name in config.checks_for(self.ctx.stage):
            code, output, seconds = dt.run_check(config, config.checks[name])   # plain timeout
            items.append(Item(name, code == 0, tail(output), code, seconds))
        return items

    def generated_items(self, before: set[str] | None) -> list[Item]:
        """Files the gate's own checks wrote: otherwise accepted would not mean pushable."""
        after = self.tree() if before is not None else None
        if before is None or after is None:
            return []
        new = sorted(after - before)
        return [Item("generated", not new, "" if not new else
                     "the checks wrote files the repository does not ignore: " + ", ".join(new[:20])
                     + (" ..." if len(new) > 20 else "") + "; add them to .gitignore")]

    def adr_items(self) -> list[Item]:
        ctx, config = self.ctx, self.ctx.config
        if ctx.stage == "plan":
            return []
        folder, required = h.WORKSPACE / config.adr_dir, ctx.stage in config.adr_required
        if not folder.is_dir():
            return [Item("adr", False, f"{config.adr_dir}/ does not exist; this stage must record "
                         "its decision as an ADR")] if required else []
        changed, since = None, "the base branch"
        if required and config.git:
            try:
                if ctx.start:               # the agent's own commits since the stage began, or uncommitted
                    since = f"the stage started ({ctx.start[:12]})"
                    changed = dt.agent_changes(config, config.adr_dir, ctx.start)
                else:
                    since = config.git.base
                    changed = dt.changed_paths(config, config.adr_dir)
            except dt.UnsafeConfig as err:
                return [Item("adr", False, str(err))]
            if changed is None:
                return [Item("adr", False, f"cannot compare {config.adr_dir}/ with {since}; if the history "
                             f"was rewritten, delete {stage_state(config, ctx.stage, ctx.branch)} and start "
                             "the stage again")]
        try:
            problems = adr_lint.lint(folder, changed=changed, since=since)
        except OSError as err:
            problems = [f"{config.adr_dir}: {err}"]
        return [Item("adr", not problems, "\n".join(problems))]


def write_report(ctx: Context, attempt: int, items: list[Item], passed: bool) -> None:
    lines = [f"# Gate report: stage {ctx.stage}, attempt {attempt}: {'PASSED' if passed else 'REJECTED'}",
             "", f"Run {ctx.run_id}, branch {ctx.branch}. Checked by the harness, not by the model.", ""]
    for i in items:
        timing = (f" (exit {i.exit}, {i.seconds:.0f} s)" if i.exit is not None
                  else f" ({i.seconds:.0f} s)" if i.seconds else "")
        lines.append(f"## {i.name}: {'passed' if i.ok else 'FAILED'}{timing}")
        if i.detail and not i.ok:
            lines += ["", "```", tail(i.detail), "```"]
        lines.append("")
    if not passed:
        tools = TOOLS.get(ctx.stage, ())
        steps = (["Fix these problems"] + (["run the checks again with run_checks"] if "run_checks" in tools else [])
                 + (["commit with git_commit"] if "git_commit" in tools else []))
        lines.append(", ".join(steps) + ", then finish.")
    path = h.inside_workspace(REPORT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def stage_state(config: dt.Config, stage: str, branch: str) -> Path:
    """Where the stage's starting commit is remembered: outside the workspace, per stage and branch."""
    return dt.git_state(config) / "stages" / f"{stage}--{branch.replace('/', '__')}.json"


def stage_start(config: dt.Config, stage: str, branch: str) -> str | None:
    """The commit the stage started from, kept across re-runs until the stage is accepted."""
    path = stage_state(config, stage, branch)
    if path.is_file():
        try:
            recorded = json.loads(path.read_text(encoding="utf-8")).get("start") or None
        except ValueError:
            recorded = None
        if recorded:                           # it must still be a commit behind HEAD on this branch
            known = dt.run_git(config, ["cat-file", "-e", f"{recorded}^{{commit}}"], timeout=30).returncode == 0
            ancestor = known and dt.run_git(config, ["merge-base", "--is-ancestor", recorded, "HEAD"],
                                            timeout=30).returncode == 0
            if not ancestor:
                raise ValueError(f"the remembered start {recorded[:12]} of stage {stage} on {branch} is not "
                                 f"in this branch's history; delete {path} to start the stage afresh")
            return recorded
    start = dt.head_commit(config)
    if start:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stage": stage, "branch": branch, "start": start}), encoding="utf-8")
    return start


def clear_agent_files(stage: str, branch: str, continuing: bool) -> None:
    """A stage starts without another stage's verdict or text; a re-run keeps its own report."""
    report = workspace_file(REPORT) or ""
    own = report.startswith(f"# Gate report: stage {stage},") and f"branch {branch}." in report
    if not (continuing and own):
        h.inside_workspace(REPORT).unlink(missing_ok=True)
    if stage in COMMIT_STAGES and not continuing:
        for stale in (PR_FILE, PR_BODY):
            h.inside_workspace(stale).unlink(missing_ok=True)


# ---------------------------------------------------------------- console
_lines: queue.Queue[str] = queue.Queue()
_reader: threading.Thread | None = None


def console_available() -> bool:
    return bool(sys.stdin) and sys.stdin.isatty()


def read_line(timeout: float) -> str | None:
    """One line typed after the prompt, within the timeout; None without a console or an answer."""
    global _reader
    if not console_available():
        return None
    if _reader is None:                     # one reader for the whole process: no lost or doubled lines
        _reader = threading.Thread(target=lambda: [_lines.put(line) for line in iter(sys.stdin.readline, "")],
                                   daemon=True)
        _reader.start()
    while not _lines.empty():               # anything typed before the question is not an answer
        _lines.get_nowait()
    try:
        return _lines.get(timeout=timeout)
    except queue.Empty:
        return None


def console_operator(name: str, args: dict) -> bool:
    """The approval prompt: a person types y within the timeout, or the action is refused."""
    detail = args.get("command") or json.dumps(args)
    print(f"\n[approval] {name}: {detail}\nApprove? [y/N] ", end="", file=sys.stderr, flush=True)
    answer = read_line(h.time_left(APPROVAL_TIMEOUT))
    if answer is None:
        print("no answer: refused", file=sys.stderr, flush=True)
        return False
    return answer.strip().lower() in ("y", "yes")


# ---------------------------------------------------------------- push
def default_branch(config: dt.Config, run_id: str) -> str:
    if config.git:
        head = dt.run_git(config, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=30)
        current = head.stdout.strip()
        if head.returncode == 0 and current not in ("", "HEAD") and not dt.branch_problem(config, current):
            return current
    return f"agent/{run_id}"


def pr_text(ctx: Context) -> tuple[str, str]:
    """Title and body from .agent/pr.md, or composed from the feature list and the report."""
    text = workspace_file(PR_FILE)
    if text and text.strip():
        lines = text.strip().splitlines()
        return lines[0].strip().lstrip("#").strip()[:120], "\n".join(lines[1:]).strip()
    features = workspace_file(ctx.features) or ""
    chosen = [re.sub(r"^\s*(?:#+\s*)?(?:\d+\.\s*)?|\s*\(this run\)\s*", "", line, flags=re.IGNORECASE).strip()
              for line in features.splitlines() if "(this run)" in line.lower()]
    title = chosen[0] if chosen else f"Changes on {ctx.branch}"
    body = ("Features in this change:\n" + "\n".join(f"- {c}" for c in chosen)) if chosen else \
        "Changes by the delivery agent."
    report = workspace_file(REPORT)
    return title[:120], body + (f"\n\n{report}" if report else "")


def push(ctx: Context) -> str:
    """Ask on the console, then push the branch and open the pull request."""
    title, body = pr_text(ctx)
    pr_path = h.inside_workspace(PR_FILE)
    if not pr_path.is_file():
        pr_path.parent.mkdir(parents=True, exist_ok=True)
        pr_path.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
    body_path = h.inside_workspace(PR_BODY)     # the body alone: the title goes in its own field
    body_path.write_text(body + "\n", encoding="utf-8")
    if not console_available():
        return "push skipped: no console to approve it"
    git = ctx.config.git
    if not console_operator("git_push_pr", {"branch": ctx.branch, "remote": git.remote,
                                            "base": git.base, "title": title}):
        return "push skipped: not approved on the console"
    return dt.git_push_pr(ctx.branch, title, PR_BODY)


def push_only(config: dt.Config, branch: str, run_id: str, args) -> tuple[str, str]:
    """Push an accepted branch without running the agent: (status, what happened)."""
    if config.git is None:
        raise ValueError("--push-only needs a git block in the delivery config")
    problem = dt.branch_problem(config, branch)
    if problem:
        raise ValueError(problem.removeprefix("ERROR: "))
    problems = dt.git_problems(config, branch)
    if problems:
        return "unpushed", "push skipped, the branch is not ready: " + "; ".join(problems)
    text = push(Context(config, "push", branch, args.plan, args.features, run_id))
    return ("pushed" if push_ok(text) else "unpushed"), text


def push_ok(text: str) -> bool:
    """Pushed, and the pull request is open (or none was configured)."""
    return text.startswith("pushed") and "could not be opened" not in text


# ---------------------------------------------------------------- entry point
def preflight(config: dt.Config, stage: str, branch: str) -> None:
    """Conditions the agent cannot fix: fail now instead of after the whole ladder."""
    if stage in COMMIT_STAGES:
        if config.git is None:
            raise ValueError(f"the {stage} stage commits, so the delivery config needs a git block")
        problem = dt.branch_problem(config, branch)
        if problem:
            raise ValueError(problem.removeprefix("ERROR: "))
        head = dt.run_git(config, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=30).stdout.strip()
        exists = dt.run_git(config, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                            timeout=30).returncode == 0
        if exists and head != branch:
            raise ValueError(f"branch {branch} exists but '{head}' is checked out; "
                             "check it out or choose another branch")
    missing = sorted({name for check in config.checks_for(stage) for name in config.checks[check].env
                      if name not in os.environ})
    if missing:
        raise ValueError(f"the {stage} gate's checks need {', '.join(missing)} exported in this environment")


def main(argv: list[str] | None = None) -> int:
    cli = h.argument_parser(description="Run one delivery stage and judge it with a gate.")
    cli.add_argument("--stage", choices=dt.STAGES, help="the stage to run")
    cli.add_argument("--push-only", action="store_true",
                     help="push the branch and open the pull request without running the agent; "
                          "export the token for this command alone")
    cli.add_argument("--effort", choices=h.LADDER, default="medium", help="first level tried")
    cli.add_argument("--stop", choices=h.LADDER, default="high", help="highest level tried")
    cli.add_argument("--branch", default="", help="feature branch (default: the checked-out one)")
    cli.add_argument("--plan", default=PLAN, help="plan file inside the workspace")
    cli.add_argument("--features", default=FEATURES, help="feature list inside the workspace")
    cli.add_argument("--run-id", default="", help="name for the trace, plan and checkpoint")
    cli.add_argument("--result", default="", metavar="FILE", help="write the outcome as JSON")
    cli.add_argument("--note", default="", help="extra instructions appended to the stage task")
    cli.add_argument("--push", action="store_true",
                     help="after an accepted build, pipeline or quality stage, ask to push and open the "
                          "pull request; the token variable is then present during the whole run, "
                          "so prefer --push-only")
    args = cli.parse_args(argv)
    config_path = os.environ.get("AGENT_DELIVERY_CONFIG", "")
    for problem in ("" if bool(args.stage) != args.push_only else "give --stage or --push-only, not both",
                    "--stop must not be below --effort" if h.LADDER.index(args.stop) < h.LADDER.index(args.effort) else "",
                    "" if config_path else "set AGENT_DELIVERY_CONFIG to the operator's delivery config"):
        if problem:
            say(f"RUN FAILED: {problem}")
            return EXIT["failed"]
    stage = args.stage or "push"
    run_id = args.run_id or f"{stage}-{uuid.uuid4().hex[:8]}"
    h.RUN_ID.set(run_id)
    h.WORKSPACE.mkdir(parents=True, exist_ok=True)
    started, progress = time.time(), Progress()
    status, answer, pushed, branch, gate = "failed", "", "", "", None
    try:
        dt.register(config_path, adr_lint=LINT)
        config = dt.CONFIG
        branch = args.branch or default_branch(config, run_id)
        if args.push_only:
            status, pushed = push_only(config, branch, run_id, args)
            say(pushed)
        else:
            preflight(config, stage, branch)
            if console_available():
                h.ask_operator = console_operator     # otherwise the model is told nobody can approve
            h.LISTENERS.append(progress)
            continuing = config.git is not None and stage_state(config, stage, branch).is_file()
            clear_agent_files(stage, branch, continuing)
            start = None
            if config.git and (stage in COMMIT_STAGES or stage in config.adr_required):
                start = stage_start(config, stage, branch)
            adr = config.checks.get("adr")
            if start and stage in config.adr_required and adr and adr.argv[:3] == (sys.executable, "-I", str(LINT)):
                config.checks["adr"] = dt.Check("adr", adr.argv + (                # the same rule the gate applies
                    "--base", start, "--author", config.git.author_email, "--git-dir", str(config.git.git_dir),
                    "--work-tree", str(h.WORKSPACE)), adr.timeout, adr.env)
            ctx = Context(config, stage, branch, args.plan, args.features, run_id, args.note, start)
            gate = Gate(ctx, progress)
            tools = [name for name in TOOLS[stage] if name in h.REGISTRY]
            answer = h.run_escalating(task_for(ctx), f"{h.orchestrator_system()}\n\n{RULES}", tools,
                                      start=args.effort, accept=gate, stop=args.stop)
            if gate.judged_run != progress.runs:        # the ladder ended at a limit before accept ran
                gate.evaluate(answer)
            status = "accepted" if gate.passed else "stopped" if h.stopped(answer) else "rejected"
            if status == "accepted" and config.git:
                stage_state(config, stage, branch).unlink(missing_ok=True)
            if args.push and status == "accepted" and config.git and stage in COMMIT_STAGES:
                pushed = push(ctx)
                say(pushed)
                if not push_ok(pushed):
                    status = "unpushed"
            elif args.push:
                say("--push applies to an accepted build, pipeline or quality stage with a git block")
    except Exception as err:
        status = "failed"
        say(f"RUN FAILED: {type(err).__name__}: {err}")
    finally:
        h.LISTENERS[:] = [listener for listener in h.LISTENERS if listener is not progress]
        h.ask_operator = h.no_operator
        dt.close()
    if args.result:
        Path(args.result).write_text(json.dumps({
            "run": run_id, "stage": stage, "status": status, "exit_code": EXIT[status],
            "branch": branch, "effort": {"start": args.effort, "stop": args.stop,
                                         "reached": progress.efforts[-1] if progress.efforts else None},
            "gate": None if gate is None else {
                "passed": gate.passed, "attempts": gate.attempt,
                "items": [{"name": i.name, "ok": i.ok, "exit": i.exit, "seconds": round(i.seconds, 1),
                           "detail": tail(i.detail, 1000)} for i in gate.items]},
            "answer": answer, "push": pushed, "push_ok": push_ok(pushed) if pushed else None,
            "seconds": round(time.time() - started, 1)}, indent=2), encoding="utf-8")
    print(f"{'push' if args.push_only else 'stage ' + stage}: {status}" + (f" on {branch}" if branch else "")
          + (f"; report in {REPORT}" if gate is not None and gate.attempt else "")
          + (f"\n{pushed}" if pushed else ""))
    return EXIT[status]


if __name__ == "__main__":
    sys.exit(main())
