"""Delivery tools, gate and stage runner against the mock endpoint and a real git repository.

Run: python tests/test_delivery.py        (needs git on PATH; no network is used)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "checks"))
sys.path.insert(0, str(ROOT / "tests"))

import mock_llm  # noqa: E402

server, port = mock_llm.start()
tmp = Path(tempfile.mkdtemp(prefix="harness-delivery-"))
workspace, state = tmp / "workspace", tmp / "delivery"
state.mkdir()
os.environ.update(
    LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
    AGENT_WORKSPACE=str(workspace), AGENT_SKILLS=str(ROOT / "skills"),
    AGENT_TRACE=str(tmp / "trace.jsonl"), AGENT_CHECKPOINTS=str(tmp / "checkpoints"),
    AGENT_MAX_STEPS="12", PASS_PROBE="passed-through", SECRET_PROBE="must-not-leak")
os.environ.pop("GH_TOKEN", None)

import adr_lint  # noqa: E402
import deliver  # noqa: E402
import delivery_tools as dt  # noqa: E402
import mini_harness as h  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def events(kind: str, run: str | None = None) -> list[dict]:
    return [e for e in map(json.loads, h.TRACE_FILE.read_text().splitlines())
            if e["event"] == kind and (run is None or e["run"] == run)]


# ---------------------------------------------------------------- a target repository
GIT_DIR, HOME, BARE = state / "target.git", state / "home", state / "remote.git"
HOME.mkdir()
(state / "gitconfig").touch()
GIT_ENV = {**os.environ, "HOME": str(HOME), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": str(state / "gitconfig"), "GIT_TERMINAL_PROMPT": "0"}


def git(*args: str, git_dir: Path = GIT_DIR) -> subprocess.CompletedProcess:
    """The test's own git commands: no hooks either, so they cannot litter the workspace."""
    return subprocess.run(["git", f"--git-dir={git_dir}", f"--work-tree={workspace}", "-c", "user.name=Tester",
                           "-c", "user.email=tester@example.invalid", "-c", f"core.hooksPath={state / 'no-hooks'}",
                           *args], env=GIT_ENV, capture_output=True, text=True, timeout=60)


def remote_branches() -> list[str]:
    listed = subprocess.run(["git", f"--git-dir={BARE}", "branch", "--list", "--format=%(refname:short)"],
                            env=GIT_ENV, capture_output=True, text=True, timeout=60).stdout
    return listed.split()


subprocess.run(["git", "init", "-q", "-b", "main", f"--separate-git-dir={GIT_DIR}", str(workspace)],
               env=GIT_ENV, check=True, capture_output=True, timeout=60)
subprocess.run(["git", "init", "-q", "--bare", str(BARE)], env=GIT_ENV, check=True, capture_output=True, timeout=60)
(workspace / "README.md").write_text("# Target\n")
(workspace / "docs").mkdir()
(workspace / "docs" / "plan.md").write_text("# Plan\n\nA greeting endpoint, then a metrics page.\n")
git("add", "-A")
git("commit", "-q", "-m", "initial")
hooks = GIT_DIR / "hooks"
hooks.mkdir(exist_ok=True)
for hook in ("pre-commit", "post-commit", "post-checkout", "pre-push"):
    (hooks / hook).write_text(f"#!/bin/sh\necho ran > hook-{hook}.txt\nexit 0\n")
    os.chmod(hooks / hook, 0o755)

TESTS_CHECK = [sys.executable, "-c", "import pathlib, sys\np = pathlib.Path('calc.py')\n"
               "t = p.read_text().strip() if p.exists() else ''\n"
               "sys.exit(0 if t == 'X = 2' else 'calc.py must define X = 2')"]
ENV_CHECK = [sys.executable, "-c", "import os\nprint('HOME=' + os.environ.get('HOME', ''))\n"
             "print('SECRET_PROBE=' + str('SECRET_PROBE' in os.environ))\n"
             "print('PASS_PROBE=' + os.environ.get('PASS_PROBE', '-'))\n"
             "print('KEYS=' + ','.join(sorted(os.environ)))"]


def write_config(path: Path, **overrides) -> Path:
    config = {"home": str(HOME),
              "checks": {"tests": {"argv": TESTS_CHECK, "timeout": 60},
                         "env": {"argv": ENV_CHECK, "timeout": 30, "env": ["PASS_PROBE"]},
                         "slow": {"argv": [sys.executable, "-c", "import time; time.sleep(5)"], "timeout": 1},
                         "needs-token": {"argv": [sys.executable, "-c", "print('ran')"], "timeout": 10,
                                         "env": ["DELIVERY_TEST_TOKEN"]}},
              "gate": ["tests"],
              "git": {"git_dir": str(GIT_DIR), "remote": str(BARE), "base": "main",
                      "protected": ["main", "release/*"], "author": "Delivery Agent <agent@example.invalid>"},
              "adr": {"dir": "docs/adr", "require_changed": ["platform", "pipeline", "quality"]}}
    config.update(overrides)
    path.write_text(json.dumps(config))
    return path


CONFIG = write_config(state / "config.json")
LINT = ROOT / "harness" / "checks" / "adr_lint.py"
GIT_BLOCK = json.loads(CONFIG.read_text())["git"]

# ---------------------------------------------------------------- 1. configuration
inside = workspace / "config.json"
inside.write_text(CONFIG.read_text())
try:
    dt.load_config(str(inside))
    refused_inside = False
except ValueError:
    refused_inside = True
inside.unlink()
check("a delivery config inside the workspace is refused", refused_inside)


def rejects(mutate) -> bool:
    raw = json.loads(CONFIG.read_text())
    mutate(raw)
    bad = state / "bad.json"
    bad.write_text(json.dumps(raw))
    try:
        dt.load_config(str(bad))
        return False
    except ValueError:
        return True


cases = {
    "unknown key": lambda r: r.update(extra=1),
    "argv must be a list": lambda r: r["checks"]["tests"].update(argv="pytest"),
    "gate names a missing check": lambda r: r.update(gate=["nope"]),
    "stage_gates needs a stage": lambda r: r.update(stage_gates={"deploy": ["tests"]}),
    "check names are lowercase words": lambda r: r["checks"].update({"Tests!": {"argv": ["x"]}}),
    "remote is https or a folder": lambda r: r["git"].update(remote="git@github.com:o/r.git"),
    "remote carries no credentials": lambda r: r["git"].update(remote="https://user:pw@github.com/o/r.git"),
    "git_dir is a git dir": lambda r: r["git"].update(git_dir=str(state)),
    "adr dir stays inside the workspace": lambda r: r.update(adr={"dir": "../adr"}),
    "env entries are variable names": lambda r: r["checks"]["env"].update(env=["BAD NAME"]),
    "timeouts are at least a second": lambda r: r["checks"]["tests"].update(timeout=0),
    "author has a name and an email": lambda r: r["git"].update(author="nobody"),
    "repo is owner/name": lambda r: r["git"].update(repo="just-a-name"),
    "git config keys are setting names": lambda r: r["git"].update(config={"bad key": "x"}),
    "git config values are one line": lambda r: r["git"].update(config={"http.proxy": "a\nb"}),
}
wrong = [name for name, mutate in cases.items() if not rejects(mutate)]
check("invalid delivery configs are refused", not wrong, str(wrong))
cfg = dt.load_config(str(CONFIG))
check("a valid config loads, the base branch is always protected and gates default per stage",
      cfg.git.protected == ("main", "release/*") and cfg.checks_for("build") == ("tests",)
      and cfg.checks_for("quality") == ("tests",) and cfg.checks_for("plan") == ()
      and cfg.home == HOME.resolve() and cfg.adr_required == ("platform", "pipeline", "quality")
      and cfg.git.config == (), str(cfg))
example = json.loads((ROOT / "harness" / "delivery.example.json").read_text())
check("the example config has every documented block",
      set(example) == {"home", "checks", "gate", "stage_gates", "git", "adr"}
      and set(example["gate"]) <= set(example["checks"]) and "config" in example["git"])
proxied = dt.load_config(write_config(state / "config-proxy.json",
                                      git={**GIT_BLOCK, "config": {"http.proxy": "http://proxy.example:3128"}}))
flags = dt.hardening(proxied)
check("operator git settings travel on the command line, after the hardening, and pass the scan",
      flags[-2:] == ["-c", "http.proxy=http://proxy.example:3128"] and "-c" in flags
      and "protocol.allow=never" in flags and "protocol.file.allow=always" in flags
      and "http.followRedirects=false" in flags and any(f.startswith("core.hooksPath=") for f in flags)
      and dt.config_problems(proxied) == [], f"{flags} {dt.config_problems(proxied)}")

# ---------------------------------------------------------------- 2. the ADR lint
GOOD = ("# 0001. Use Postgres\nStatus: Proposed\nDate: 2026-11-28\n\n## Context\nc\n\n## Decision\nd\n\n"
        "## Consequences\nq\n\n## Alternatives considered\na\n\n## Assumptions to confirm\n- [ ] x\n")
adr_ok = tmp / "adr-ok"
adr_ok.mkdir()
(adr_ok / "0001-use-postgres.md").write_text(GOOD)
(adr_ok / "README.md").write_text("- [0001](0001-use-postgres.md) Use Postgres\n")
check("a well-formed record and index pass the lint", adr_lint.lint(adr_ok) == [], str(adr_lint.lint(adr_ok)))
adr_bad = tmp / "adr-bad"
adr_bad.mkdir()
(adr_bad / "0001-use-postgres.md").write_text(GOOD)
(adr_bad / "0002-Bad_Name.md").write_text(GOOD.replace("0001", "0002"))
(adr_bad / "0003-no-headings.md").write_text("# 0003. Thin\nStatus: Accepted\nDate: 2026-11-28\n\n## Context\nc\n")
(adr_bad / "0004-wrong-number.md").write_text(GOOD.replace("# 0001.", "# 0005.").replace("Status: Proposed", "Status: Maybe"))
(adr_bad / "0006-too-big.md").write_text(GOOD.replace("0001", "0006") + "x" * 6000)
(adr_bad / "0007-out-of-order.md").write_text(GOOD.replace("0001", "0007").replace("## Decision\nd\n\n## Consequences\nq\n", "## Consequences\nq\n\n## Decision\nd\n"))
(adr_bad / "README.md").write_text("- [0001](0001-use-postgres.md) Use Postgres\n- [0009](0009-ghost.md) Ghost\n")
problems = adr_lint.lint(adr_bad)
wanted = ["0002-Bad_Name.md: file name must be NNNN-slug.md", "0003-no-headings.md: missing headings",
          "0004-wrong-number.md: title number 0005", "0004-wrong-number.md: needs a 'Status: '",
          "0006-too-big.md: 6", "0007-out-of-order.md: headings out of order",
          "README.md: does not list 0003-no-headings.md", "README.md: names 0009-ghost.md"]
missing = [w for w in wanted if not any(p.startswith(w) for p in problems)]
check("the lint reports every rule it enforces, and every unlisted record", not missing and len(problems) == 12
      and sum(p.startswith("README.md: does not list") for p in problems) == 5, f"missing={missing} got={problems}")
check("the lint can require a record added or changed on the branch",
      adr_lint.lint(tmp / "nowhere") == [f"{tmp / 'nowhere'}: folder not found"]
      and any("no record" in p for p in adr_lint.lint(adr_ok, changed=["docs/adr/README.md"]))
      and adr_lint.lint(adr_ok, changed=["docs/adr/0001-use-postgres.md"]) == [])
cli_ok = subprocess.run([sys.executable, "-I", str(LINT), str(adr_ok)], capture_output=True, text=True, timeout=60)
cli_bad = subprocess.run([sys.executable, "-I", str(LINT), str(adr_bad)], capture_output=True, text=True, timeout=60)
check("the lint script exits 0 with a count, or 1 with one problem per line",
      cli_ok.returncode == 0 and cli_ok.stdout.strip() == "OK: 1 records"
      and cli_bad.returncode == 1 and len(cli_bad.stdout.strip().splitlines()) == 12, cli_ok.stdout + cli_bad.stdout)

# ---------------------------------------------------------------- 3. the tools
names = dt.register(str(CONFIG), adr_lint=LINT)
check("delivery tools register with the right approval and repetition rules",
      names == ["run_checks", "git_commit", "git_push_pr"] and h.REGISTRY["run_checks"].repeatable
      and not h.REGISTRY["run_checks"].needs_approval and not h.REGISTRY["git_commit"].needs_approval
      and h.REGISTRY["git_push_pr"].needs_approval and not h.REGISTRY["git_push_pr"].repeatable
      and "adr" in dt.CONFIG.checks and "adr, env, needs-token, slow, tests" in h.REGISTRY["run_checks"].description,
      str(names))
out = dt.run_checks("env", "probe the environment")
keys = set(next(line for line in out.splitlines() if line.startswith("KEYS=")).removeprefix("KEYS=").split(","))
allowed_keys = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "PASS_PROBE", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
                "PATHEXT", "WINDIR"}
check("checks run with a private HOME, no git state and only allow-listed variables",
      out.startswith("exit=0") and f"HOME={dt.checks_home(dt.CONFIG)}" in out and "SECRET_PROBE=False" in out
      and "PASS_PROBE=passed-through" in out and keys <= allowed_keys and "PASS_PROBE" in keys
      and dt.checks_home(dt.CONFIG) != dt.git_state(dt.CONFIG)
      and not (dt.checks_home(dt.CONFIG) / "gitconfig").exists(), out)
unknown = dt.run_checks("nope", "x")
check("an unknown check is refused with the configured names",
      unknown.startswith("ERROR: no check named 'nope'") and "tests" in unknown, unknown)
token_check = dt.run_checks("needs-token", "x")
check("a check whose variable is not exported says so instead of running",
      token_check.startswith("exit=none") and "DELIVERY_TEST_TOKEN is not set" in token_check, token_check)
slow = dt.run_checks("slow", "x")
check("a check is stopped at its timeout", slow.startswith("exit=none") and "no result after 1 seconds" in slow, slow)
lint_out = dt.run_checks("adr", "lint")
check("the adr check lints the workspace's records", lint_out.startswith("exit=1") and "folder not found" in lint_out, lint_out)
check("every check leaves a trace event", {e["name"] for e in events("check")} >= {"env", "needs-token", "slow", "adr"})

seen = Counter()
same = {"name": "run_checks", "arguments": json.dumps({"name": "env", "reason": "again"})}
third = [h.execute(same, h.REGISTRY, seen) for _ in range(3)][-1]
seen = Counter()
listing = {"name": "list_dir", "arguments": json.dumps({"path": "."})}
third_listing = [h.execute(listing, h.REGISTRY, seen) for _ in range(3)][-1]
check("a repeatable tool may run the same call a third time; other tools are still stopped",
      third.startswith("exit=0") and third_listing.startswith("ERROR: this exact call has already run twice"),
      third[:60] + " | " + third_listing[:60])

check("protected and malformed branches are refused before any git command runs",
      dt.git_commit("main", "x").startswith("ERROR: 'main' is protected")
      and dt.git_commit("release/1.0", "x").startswith("ERROR: 'release/1.0' is protected")
      and dt.git_commit("bad..name", "x").startswith("ERROR: 'bad..name' is not a valid")
      and dt.git_commit("-flag", "x").startswith("ERROR") and dt.git_commit("a/.hidden", "x").startswith("ERROR")
      and dt.git_commit("feature/x", "  ") == "ERROR: a commit message is required")
(workspace / "hello.py").write_text("print('hi')\n")
(workspace / ".agent").mkdir(exist_ok=True)
(workspace / ".agent" / "plan-x.md").write_text("p")
(workspace / "__pycache__").mkdir(exist_ok=True)
(workspace / "__pycache__" / "a.pyc").write_text("x")
(workspace / "coverage.xml").write_text("<coverage/>")
(workspace / ".coverage").write_text("db")
out = dt.git_commit("feature/unit", "Add hello\n\nWhy: the test.")
log = git("log", "--format=%an <%ae> %s", "-1").stdout.strip()
files = git("show", "--name-only", "--format=", "HEAD").stdout.split()
check("git_commit creates the branch, commits as the configured author and leaves state, caches and reports out",
      out.startswith("committed on feature/unit:") and git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/unit"
      and log == "Delivery Agent <agent@example.invalid> Add hello" and files == ["hello.py"], f"{out} | {log} | {files}")
check("hooks in the git dir never run for the agent's git commands",
      not list(workspace.glob("hook-*.txt")) and (dt.git_state(dt.CONFIG) / "gitconfig").read_bytes() == b"")
check("a second call with nothing new says so",
      dt.git_commit("feature/unit", "again") == "nothing to commit on feature/unit: every change is already committed")
(workspace / "other.txt").write_text("o\n")
moved = dt.git_commit("feature/other", "Add other")
back = dt.git_commit("feature/unit", "x")
check("a new branch starts from the current head; switching to another existing branch is refused",
      moved.startswith("committed on feature/other") and git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/other"
      and back.startswith("ERROR: branch feature/unit exists but 'feature/other' is checked out"), f"{moved} | {back}")
check("commit events are traced", [e["branch"] for e in events("commit")] == ["feature/unit", "feature/other"])

repo_config = GIT_DIR / "config"
original_config = repo_config.read_text()
repo_config.write_text(original_config + '[url "http://evil.example/"]\n\tinsteadOf = https://github.com/\n')
(workspace / "tamper.txt").write_text("t\n")
refused_commit = dt.git_commit("feature/other", "x")
refused_gate = dt.git_problems(dt.CONFIG, "feature/other")
repo_config.write_text(original_config)
(workspace / "tamper.txt").unlink()
check("a URL rewrite in the repository's git config stops every git command and the gate",
      refused_commit.startswith("ERROR: git configuration refused:") and "url.http://evil.example/.insteadof" in refused_commit
      and len(refused_gate) == 1 and "insteadof" in refused_gate[0]
      and git("status", "--porcelain", "--", "tamper.txt").stdout == "", f"{refused_commit} | {refused_gate}")
verdicts = {}
for label, block in {
        "url-named remote": '[remote "https://github.com/o/r.git"]\n\turl = https://github.com/o/r.git\n',
        "push url": '[remote "origin"]\n\turl = https://github.com/o/r.git\n\tpushurl = https://evil.example/x.git\n',
        "plain nickname": '[remote "origin"]\n\turl = https://github.com/o/r.git\n'}.items():
    repo_config.write_text(original_config + block)
    verdicts[label] = dt.config_problems(dt.CONFIG)
repo_config.write_text(original_config)
check("a remote named by a URL or carrying a push URL is refused; an ordinary remote is not",
      len(verdicts["url-named remote"]) == 1 and "remote.https://github.com/o/r.git.url" in verdicts["url-named remote"][0]
      and len(verdicts["push url"]) == 1 and "pushurl" in verdicts["push url"][0] and verdicts["plain nickname"] == [],
      str(verdicts))

wrong_branch = dt.git_problems(dt.CONFIG, "feature/unit")
(workspace / "dirty.txt").write_text("d\n")
dirty = dt.git_problems(dt.CONFIG, "feature/other")
(workspace / "dirty.txt").unlink()
check("the git gate explains the wrong branch and uncommitted files, and passes a clean committed branch",
      any("HEAD is on 'feature/other' instead of feature/unit" in p for p in wrong_branch)
      and any("uncommitted changes: dirty.txt" in p for p in dirty) and dt.git_problems(dt.CONFIG, "feature/other") == [],
      f"{wrong_branch} | {dirty}")
main_sha, head_sha = git("rev-parse", "main").stdout.strip(), dt.head_commit(dt.CONFIG)
check("changes are found against the base branch or against a given commit, committed or not",
      "other.txt" in dt.changed_paths(dt.CONFIG, ".") and "hello.py" in dt.changed_paths(dt.CONFIG, ".", since=main_sha)
      and dt.changed_paths(dt.CONFIG, ".", since=head_sha) == [] and head_sha == git("rev-parse", "HEAD").stdout.strip(),
      str(dt.changed_paths(dt.CONFIG, ".")))

with patch.object(h, "ask_operator", return_value=False):
    denied = h.execute({"name": "git_push_pr", "arguments": json.dumps(
        {"branch": "feature/other", "title": "T", "body_path": ""})}, h.REGISTRY, Counter())
check("a push needs the operator's approval", denied.startswith("DENIED") and "feature/other" not in remote_branches(), denied)
check("protected or missing branches cannot be pushed",
      dt.git_push_pr("main", "T", "").startswith("ERROR: 'main' is protected")
      and dt.git_push_pr("feature/none", "T", "").startswith("ERROR: there is no local branch")
      and dt.git_push_pr("feature/other", " ", "") == "ERROR: a pull request title is required")
pushed = dt.git_push_pr("feature/other", "Add other", "")
check("a local remote receives the branch, no hook runs and no pull request is attempted",
      pushed.startswith("pushed feature/other to") and "open the pull request by hand" in pushed
      and "feature/other" in remote_branches() and [e["branch"] for e in events("push")] == ["feature/other"]
      and not list(workspace.glob("hook-*.txt")), pushed)

dt.close()
check("close removes the tools", not {"run_checks", "git_commit", "git_push_pr"} & set(h.REGISTRY) and dt.CONFIG is None)
try:
    with patch.object(dt, "HELPER", workspace / "git_credential.py"):
        dt.register(str(CONFIG))
    helper_inside = False
except ValueError:
    helper_inside = True
dt.close()
check("the helper, the harness and the interpreter must live outside the workspace", helper_inside)
HTTPS = write_config(state / "config-https.json", git={**GIT_BLOCK, "remote": "https://github.com/o/r.git", "repo": "o/r"})
dt.register(str(HTTPS))
check("an https push without the token is refused before anything runs",
      dt.git_push_pr("feature/other", "T", "").startswith("ERROR: GH_TOKEN is not set"))
os.environ["GH_TOKEN"] = "t0ken-secret"
pushes: list[tuple[list[str], dict | None]] = []
real_run_git = dt.run_git


def fake_run_git(config, args, timeout=60, extra_env=None, scan=True):
    if "ls-remote" in args:
        url = "http://evil.example/o/r.git" if os.environ.get("PUSH_MODE") == "rewrite" else config.git.remote
        return subprocess.CompletedProcess(args, 0, url + "\n", "")
    if "push" in args:
        pushes.append((args, extra_env))
        code = 1 if os.environ.get("PUSH_MODE") == "fail" else 0
        return subprocess.CompletedProcess(args, code, "", "remote: rejected t0ken-secret\n" if code else "")
    return real_run_git(config, args, timeout, extra_env, scan)


with patch.object(dt, "run_git", fake_run_git), \
        patch.object(dt, "open_pull_request", return_value="https://github.com/o/r/pull/7") as opened_pr:
    opened = dt.git_push_pr("feature/other", "Add other", "")
args, env = pushes[0]
check("an https push uses the credential helper, keeps the token out of argv and opens the pull request",
      opened == "pushed feature/other and opened the pull request: https://github.com/o/r/pull/7"
      and env == {"DELIVERY_TOKEN": "t0ken-secret", "DELIVERY_HOST": "github.com"}
      and args[:3] == ["-c", "credential.helper=", "-c"] and args[3].startswith("credential.helper=!")
      and " -I -S " in args[3] and "git_credential.py" in args[3] and "--no-verify" in args
      and "t0ken-secret" not in " ".join(args) and args[-1] == "refs/heads/feature/other:refs/heads/feature/other"
      and args[-2] == "https://github.com/o/r.git" and opened_pr.call_args.args[1:] == ("t0ken-secret", "feature/other", "Add other", ""),
      f"{opened} | {args}")
with patch.object(dt, "run_git", fake_run_git), \
        patch.object(dt, "open_pull_request", side_effect=RuntimeError("GitHub answered 403 for t0ken-secret")):
    half = dt.git_push_pr("feature/other", "Add other", "")
os.environ["PUSH_MODE"] = "fail"
with patch.object(dt, "run_git", fake_run_git):
    rejected = dt.git_push_pr("feature/other", "Add other", "")
os.environ["PUSH_MODE"] = "rewrite"
with patch.object(dt, "run_git", fake_run_git):
    rewritten = dt.git_push_pr("feature/other", "Add other", "")
del os.environ["PUSH_MODE"]
check("a failed pull request or push is reported with the token redacted",
      half.startswith("pushed feature/other, but the pull request could not be opened") and "t0ken-secret" not in half
      and rejected.startswith("ERROR: push failed (exit 1)") and "***" in rejected and "t0ken-secret" not in rejected,
      f"{half} | {rejected}")
check("a push whose URL git would rewrite is refused before it runs",
      rewritten.startswith("ERROR: git would push to 'http://evil.example/o/r.git' instead") and len(pushes) == 3, rewritten)
del os.environ["GH_TOKEN"]
dt.close()
helper = [sys.executable, "-I", "-S", str(ROOT / "harness" / "git_credential.py"), "get"]
clean = {k: v for k, v in os.environ.items() if k not in ("DELIVERY_TOKEN", "DELIVERY_HOST")}


def ask_helper(request: str, **env: str) -> str:
    return subprocess.run(helper, input=request, capture_output=True, text=True, env={**clean, **env}, timeout=60).stdout


check("the credential helper answers only for the configured host over https, from its own environment",
      ask_helper("protocol=https\nhost=github.com\n\n", DELIVERY_TOKEN="abc", DELIVERY_HOST="github.com")
      == "username=x-access-token\npassword=abc\n"
      and ask_helper("protocol=https\nhost=evil.example\n\n", DELIVERY_TOKEN="abc", DELIVERY_HOST="github.com") == ""
      and ask_helper("protocol=http\nhost=github.com\n\n", DELIVERY_TOKEN="abc", DELIVERY_HOST="github.com") == ""
      and ask_helper("protocol=https\nhost=github.com\n\n", DELIVERY_TOKEN="abc") == ""
      and ask_helper("protocol=https\nhost=github.com\n\n", DELIVERY_HOST="github.com") == "")

# ---------------------------------------------------------------- 4. the stage runner
git("checkout", "-q", "main")
deliver.console_available = lambda: True
deliver.console_operator = lambda name, args: False
os.environ["AGENT_DELIVERY_CONFIG"] = str(CONFIG)
result = tmp / "result.json"
code = deliver.main(["--stage", "plan", "--run-id", "plan-1", "--result", str(result), "--stop", "medium",
                     "--note", "[scenario:delivery_plan] nothing chosen"])
report = json.loads(result.read_text())
gate_report = (workspace / ".agent" / "gate-report.md").read_text()
check("a plan with nothing chosen is rejected: exit code 1, a report for the person and the run",
      code == 1 and report["status"] == "rejected" and report["exit_code"] == 1
      and gate_report.startswith("# Gate report: stage plan, attempt 1: REJECTED") and "## features: FAILED" in gate_report
      and [e["passed"] for e in events("gate", "plan-1")] == [False], gate_report[:300])
code = deliver.main(["--stage", "plan", "--run-id", "plan-2", "--result", str(result), "--stop", "medium",
                     "--note", "[scenario:delivery_plan]"])
report = json.loads(result.read_text())
features = (workspace / "docs" / "plan" / "features.md").read_text()
check("the plan stage is accepted when a feature is chosen",
      code == 0 and report["status"] == "accepted" and report["run"] == "plan-2" and report["effort"]["reached"] == "medium"
      and [i["name"] for i in report["gate"]["items"]] == ["features"] and "(this run)" in features
      and report["answer"] == "DONE: plan", json.dumps(report)[:400])
check("the stage loaded the feature-planning skill and left the plan alone",
      any(e["tool"] == "load_skill" for e in events("tool", "plan-2"))
      and (workspace / "docs" / "plan.md").read_text().startswith("# Plan")
      and [e["stopped"] for e in events("answer", "plan-2")] == [False])
code = deliver.main(["--stage", "plan", "--run-id", "plan-3", "--result", str(result), "--stop", "medium",
                     "--note", "[scenario:delivery_plan_shell]"])
shell_events = [e for e in events("tool", "plan-3") if e["tool"] == "run_shell"]
check("tools the stage does not need are withheld, and the model is told so",
      code == 0 and json.loads(result.read_text())["answer"].startswith("DONE: ERROR: unknown tool 'run_shell'")
      and len(shell_events) == 1 and shell_events[0]["failed"], json.loads(result.read_text())["answer"])

code = deliver.main(["--stage", "platform", "--run-id", "platform-1", "--result", str(result), "--stop", "medium",
                     "--note", "[scenario:delivery_platform]"])
report = json.loads(result.read_text())
check("the platform stage is accepted: the proposed ADR exists, passes the lint and was added since the stage began",
      code == 0 and report["status"] == "accepted" and [i["name"] for i in report["gate"]["items"]] == ["platform-adr", "adr"]
      and report["answer"].startswith("DONE: platform exit=0") and (workspace / "docs" / "adr" / "0001-platform.md").exists()
      and not list((dt.git_state(cfg) / "stages").glob("platform--*")), json.dumps(report)[:400])

code = deliver.main(["--stage", "build", "--branch", "feature/calc", "--run-id", "build-1", "--result", str(result),
                     "--note", "[scenario:delivery_build]"])
report = json.loads(result.read_text())
gates = events("gate", "build-1")
check("the build stage escalates once and is accepted after the agent reads the gate report",
      code == 0 and report["status"] == "accepted" and [e["effort"] for e in events("run", "build-1")] == ["medium", "high"]
      and [g["passed"] for g in gates] == [False, True] and report["effort"]["reached"] == "high"
      and (workspace / "calc.py").read_text() == "X = 2\n", json.dumps(report)[:400])
check("the git state is judged before the checks run; the first attempt failed only the tests",
      [(i["name"], i["ok"]) for i in gates[0]["items"]] == [("git", True), ("tests", False), ("generated", True), ("adr", True)]
      and gates[0]["items"][1]["exit"] == 1 and all(i["ok"] for i in gates[1]["items"])
      and (workspace / ".agent" / "gate-report.md").read_text().startswith("# Gate report: stage build, attempt 2: PASSED"),
      str(gates))
tool_events = [e for e in events("tool", "build-1") if e["tool"] == "run_checks"]
check("three identical test runs were allowed in each attempt", len(tool_events) == 6 and not any(e["failed"] for e in tool_events))
subjects = git("log", "--format=%s", "main..HEAD").stdout.splitlines()
check("the feature branch holds the agent's commits, nothing is left uncommitted and the stage memory is cleared",
      git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/calc" and subjects == ["Add calc", "Add calc"]
      and git("status", "--porcelain", "--", ".", *dt.excludes()).stdout.strip() == ""
      and not (dt.git_state(cfg) / "stages" / "build--feature__calc.json").exists(), str(subjects))

git("checkout", "-q", "main")
code = deliver.main(["--stage", "build", "--branch", "feature/calc", "--run-id", "build-pre", "--result", str(result)])
check("a branch that exists but is not checked out fails the stage at once, before any model call",
      code == 3 and json.loads(result.read_text())["status"] == "failed" and not events("run", "build-pre"))
git("checkout", "-q", "feature/calc")

code = deliver.main(["--stage", "build", "--branch", "feature/calc", "--run-id", "build-2", "--result", str(result),
                     "--stop", "medium", "--push", "--note", "[scenario:delivery_build] already fixed"])
report = json.loads(result.read_text())
check("an accepted stage whose push is refused exits 4 and says so",
      code == 4 and report["status"] == "unpushed" and report["push"] == "push skipped: not approved on the console"
      and report["push_ok"] is False and "feature/calc" not in remote_branches(), json.dumps(report)[:400])
deliver.console_operator = lambda name, args: name == "git_push_pr"
code = deliver.main(["--push-only", "--branch", "feature/calc", "--run-id", "push-1", "--result", str(result)])
report = json.loads(result.read_text())
pr_file = (workspace / ".agent" / "pr.md").read_text()
check("--push-only pushes an accepted branch after a console approval and composes the pull request text",
      code == 0 and report["status"] == "pushed" and report["push"].startswith("pushed feature/calc to")
      and report["push_ok"] is True and "feature/calc" in remote_branches()
      and pr_file.startswith("Greeting endpoint\n\nFeatures in this change:\n- Greeting endpoint\n")
      and (workspace / ".agent" / "pr-body.md").read_text().startswith("Features in this change:"),
      f"{code} | {report.get('push')} | {remote_branches()} | {pr_file[:120]!r}")
check("--push-only refuses a protected branch and a branch that is not ready",
      deliver.main(["--push-only", "--branch", "main"]) == 3
      and deliver.main(["--push-only", "--branch", "feature/unit", "--result", str(result)]) == 4
      and "not ready" in json.loads(result.read_text())["push"])
deliver.console_operator = lambda name, args: False

code = deliver.main(["--stage", "pipeline", "--branch", "feature/calc", "--run-id", "pipeline-1", "--result", str(result),
                     "--note", "[scenario:delivery_pipeline]"])
report = json.loads(result.read_text())
gates = events("gate", "pipeline-1")
pipeline_tools = events("tool", "pipeline-1")
check("the pipeline stage is rejected without its ADR, then accepted once the agent records the decision",
      code == 0 and report["status"] == "accepted" and [g["passed"] for g in gates] == [False, True]
      and [(i["name"], i["ok"]) for i in gates[0]["items"]] == [("ci-workflow", True), ("git", True), ("adr", False)]
      and all(i["ok"] for i in report["gate"]["items"]) and report["effort"]["reached"] == "high"
      and (workspace / ".github" / "workflows" / "ci.yml").exists()
      and (workspace / "docs" / "adr" / "0002-github-actions-pipeline.md").exists()
      and [e["failed"] for e in pipeline_tools if e["tool"] == "read_file"] == [True, False]
      and not any(e["failed"] for e in pipeline_tools if e["tool"] in ("load_skill", "edit_file", "git_commit"))
      and not list((dt.git_state(cfg) / "stages").glob("pipeline--*")), json.dumps(report)[:400])
check("the second attempt read the report and committed only the missing record; the tree is clean",
      git("log", "--format=%s", "-2").stdout.splitlines() == ["Add the GitHub Actions pipeline"] * 2
      and git("show", "--name-only", "--format=", "HEAD").stdout.split()
      == ["docs/adr/0002-github-actions-pipeline.md", "docs/adr/README.md"]
      and git("status", "--porcelain", "--", ".", *dt.excludes()).stdout.strip() == "")
code = deliver.main(["--stage", "quality", "--branch", "feature/calc", "--run-id", "quality-1", "--result", str(result),
                     "--stop", "medium", "--note", "[scenario:delivery_quality]"])
report = json.loads(result.read_text())
check("the quality stage is accepted in one attempt: project file, gated job, passing tests and its ADR",
      code == 0 and report["status"] == "accepted" and report["effort"]["reached"] == "medium"
      and [(i["name"], i["ok"]) for i in report["gate"]["items"]] == [("sonar-project", True), ("git", True),
                                                                      ("tests", True), ("generated", True), ("adr", True)]
      and "quality:" in (workspace / ".github" / "workflows" / "ci.yml").read_text()
      and (workspace / "docs" / "adr" / "0003-quality-gate-thresholds.md").exists()
      and git("log", "--format=%s", "-1").stdout.strip() == "Add the SonarQube quality gate"
      and not any(e["failed"] for e in events("tool", "quality-1"))
      and not list((dt.git_state(cfg) / "stages").glob("quality--*")), json.dumps(report)[:400])
check("the stage runner leaves the harness as it found it",
      h.ask_operator is h.no_operator and dt.CONFIG is None and not any(isinstance(l, deliver.Progress) for l in h.LISTENERS))

dt.register(str(CONFIG), adr_lint=LINT)
start = dt.head_commit(dt.CONFIG)
ctx = deliver.Context(dt.CONFIG, "pipeline", "feature/calc", deliver.PLAN, deliver.FEATURES, "adr-rule", start=start)
gate = deliver.Gate(ctx, deliver.Progress())
before = gate.adr_items()
record, index = workspace / "docs" / "adr" / "0004-rule-check.md", workspace / "docs" / "adr" / "README.md"
original_index = index.read_text()
record.write_text(GOOD.replace("0001", "0004").replace("Use Postgres", "Rule check"))
index.write_text(original_index + "- [0004](0004-rule-check.md) Rule check\n")
after = gate.adr_items()
record.unlink()
index.write_text(original_index)
check("a stage that must record a decision is judged against its own starting commit, not the base branch",
      len(before) == 1 and not before[0].ok and "no record" in before[0].detail and "stage started" in before[0].detail
      and len(after) == 1 and after[0].ok, f"{before} | {after}")
first_start = deliver.stage_start(dt.CONFIG, "pipeline", "feature/calc")
(workspace / "docs" / "adr" / "0009-by-a-person.md").write_text(GOOD.replace("0001", "0009").replace("Use Postgres", "By a person"))
index.write_text(original_index + "- [0009](0009-by-a-person.md) By a person\n")
git("add", "-A", "--", "docs/adr")
git("commit", "-q", "-m", "A person records a decision")
second_start = deliver.stage_start(dt.CONFIG, "pipeline", "feature/calc")
person_only = dt.agent_changes(dt.CONFIG, "docs/adr", first_start)
everyone = dt.changed_paths(dt.CONFIG, "docs/adr", since=first_start)
check("a remembered start is reused across runs, and only the agent's own commits count for the ADR rule",
      first_start == start and second_start == first_start and person_only == []
      and "docs/adr/0009-by-a-person.md" in everyone, f"{first_start} {second_start} {person_only} {everyone}")
state_file = deliver.stage_state(dt.CONFIG, "pipeline", "feature/calc")
refusals = []
for bogus in ("0123456789abcdef0123456789abcdef01234567", git("rev-parse", "feature/other").stdout.strip()):
    state_file.write_text(json.dumps({"start": bogus}))
    try:
        deliver.stage_start(dt.CONFIG, "pipeline", "feature/calc")
        refusals.append(False)
    except ValueError as err:
        refusals.append("delete" in str(err))
state_file.unlink()
check("a remembered start that is unknown or not an ancestor of HEAD is refused with the file to delete", refusals == [True, True])
gen_config = write_config(state / "config-gen.json", gate=["tests", "writes"], checks={
    **json.loads(CONFIG.read_text())["checks"],
    "writes": {"argv": [sys.executable, "-c", "open('generated.txt', 'w').write('x')"], "timeout": 10}})
dt.close()
dt.register(str(gen_config), adr_lint=LINT)
gate = deliver.Gate(deliver.Context(dt.CONFIG, "build", "feature/calc", deliver.PLAN, deliver.FEATURES, "gen-rule"),
                    deliver.Progress())
gen_passed = gate.evaluate("x")
(workspace / "generated.txt").unlink()
check("files written by the gate's own checks fail the gate, so accepted means pushable",
      not gen_passed and [(i.name, i.ok) for i in gate.items] == [("git", True), ("tests", True), ("writes", True),
                                                                   ("generated", False), ("adr", True)]
      and "generated.txt" in gate.items[3].detail and ".gitignore" in gate.items[3].detail, str(gate.items))
dt.close()
dt.register(str(CONFIG), adr_lint=LINT)
deliver.console_operator = lambda name, args: name == "git_push_pr"
with patch.object(dt, "git_push_pr", return_value="pushed feature/calc, but the pull request could not be opened: 403"):
    half_code = deliver.main(["--push-only", "--branch", "feature/calc", "--run-id", "push-2", "--result", str(result)])
deliver.console_operator = lambda name, args: False
check("a push without its pull request is not a success", half_code == 4
      and json.loads(result.read_text())["status"] == "unpushed" and json.loads(result.read_text())["push_ok"] is False)
dt.register(str(CONFIG), adr_lint=LINT)
h.RUN_ID.set("worker-1")
out = h.run_agent("[scenario:delivery_worker] delegate the tests", h.orchestrator_system(), list(deliver.BUILD), effort="medium")
check("a worker can be granted run_checks", out.startswith("worker saw exit=0"), out)
dt.close()

os.environ["AGENT_DELIVERY_CONFIG"] = str(write_config(state / "config-env.json", stage_gates={"build": ["needs-token"]}))
code = deliver.main(["--stage", "build", "--branch", "feature/calc", "--run-id", "build-env", "--result", str(result)])
os.environ["AGENT_DELIVERY_CONFIG"] = str(CONFIG)
check("a gate check whose variable is not exported fails the stage before any model call",
      code == 3 and not events("run", "build-env") and json.loads(result.read_text())["status"] == "failed")

report_path, pr_path = workspace / ".agent" / "gate-report.md", workspace / ".agent" / "pr.md"
own_report = "# Gate report: stage build, attempt 1: REJECTED\n\nRun x, branch feature/calc. Checked by the harness.\n"
report_path.write_text(own_report)
pr_path.write_text("Title\n\nBody\n")
deliver.clear_agent_files("build", "feature/calc", continuing=True)
kept = report_path.exists() and pr_path.exists()
deliver.clear_agent_files("build", "feature/calc", continuing=False)
check("a re-run of a rejected stage keeps its own report and pull request text; a fresh stage starts clean",
      kept and not report_path.exists() and not pr_path.exists())
features_path = workspace / "docs" / "plan" / "features.md"
saved_features = features_path.read_text()
features_path.unlink()
code = deliver.main(["--stage", "plan", "--run-id", "plan-4", "--result", str(result), "--stop", "medium",
                     "--note", "[scenario:steps] plan never ends"])
report = json.loads(result.read_text())
for leftover in workspace.glob("s*.txt"):
    leftover.unlink()
features_path.write_text(saved_features)
check("a run that hits its step limit without passing the gate exits 2 as stopped, after a final gate verdict",
      code == 2 and report["status"] == "stopped" and report["answer"].startswith("Stopped at the 12-step limit")
      and [e["passed"] for e in events("gate", "plan-4")] == [False]
      and (workspace / ".agent" / "gate-report.md").read_text().startswith("# Gate report: stage plan, attempt 1: REJECTED"),
      json.dumps(report)[:300])

# ---------------------------------------------------------------- 5. harness additions
h.RUN_ID.set("ladder-1")
out = h.run_escalating("[scenario:think] ladder", h.orchestrator_system(), h.ORCHESTRATOR_TOOLS,
                       start="low", accept=lambda answer: False, stop="medium")
try:
    h.run_escalating("x", "y", [], start="high", stop="low")
    below_refused = False
except ValueError:
    below_refused = True
check("run_escalating stops at the named level and refuses a stop below the start",
      out.startswith("think said:") and [e["effort"] for e in events("run", "ladder-1")] == ["low", "medium"]
      and len(events("escalate", "ladder-1")) == 2 and below_refused, out)
no_config = {k: v for k, v in os.environ.items() if k != "AGENT_DELIVERY_CONFIG"}
with patch.dict(os.environ, no_config, clear=True):
    unconfigured = deliver.main(["--stage", "plan"])
try:
    deliver.main(["--stage", "bogus"])
    usage_code = 0
except SystemExit as err:
    usage_code = err.code
check("the stage runner fails cleanly on a missing config, conflicting or wrong arguments",
      unconfigured == 3 and deliver.main(["--stage", "plan", "--effort", "high", "--stop", "low"]) == 3
      and deliver.main(["--stage", "plan", "--push-only"]) == 3 and usage_code == 3)
cli = [sys.executable, str(ROOT / "harness" / "mini_harness.py")]
cli_env = dict(os.environ, AGENT_WORKSPACE=str(tmp / "cli-workspace"), AGENT_TRACE=str(tmp / "cli-trace.jsonl"),
               AGENT_CHECKPOINTS=str(tmp / "cli-checkpoints"))
done = subprocess.run(cli + ["--run-id", "cli-1", "--result", str(tmp / "cli.json"), "[scenario:basic] cli result"],
                      env=cli_env, capture_output=True, text=True, timeout=60)
written = json.loads((tmp / "cli.json").read_text())
cli_trace = [json.loads(line) for line in (tmp / "cli-trace.jsonl").read_text().splitlines()]
check("the CLI takes a run id, writes a result file and exits 0 on an answer",
      done.returncode == 0 and done.stdout.strip() == "DONE: hello" and written["status"] == "finished"
      and written["run"] == "cli-1" and written["answer"] == "DONE: hello"
      and any(e["event"] == "answer" and e["run"] == "cli-1" and e["text"] == "DONE: hello" and not e["stopped"]
              for e in cli_trace), done.stdout + done.stderr)
stopped = subprocess.run(cli + ["--run-id", "cli-2", "--result", str(tmp / "cli2.json"), "[scenario:steps] cli never ends"],
                         env={**cli_env, "AGENT_MAX_STEPS": "3"}, capture_output=True, text=True, timeout=60)
check("a run that stops at a limit exits 2 with status stopped",
      stopped.returncode == 2 and json.loads((tmp / "cli2.json").read_text())["status"] == "stopped"
      and stopped.stdout.startswith("Stopped at the 3-step limit"), stopped.stdout + stopped.stderr)
broken = subprocess.run(cli + ["--result", str(tmp / "cli3.json"), "[scenario:basic] cli broken"],
                        env={**cli_env, "LLM_API_KEY": "wrong"}, capture_output=True, text=True, timeout=60)
usage = subprocess.run(cli + ["--effort", "bogus", "task"], env=cli_env, capture_output=True, text=True, timeout=60)
check("a run that fails exits 3 with the error on stderr, and so does a usage error",
      broken.returncode == 3 and json.loads((tmp / "cli3.json").read_text())["status"] == "failed"
      and broken.stderr.startswith("RUN FAILED:") and broken.stdout == "" and usage.returncode == 3
      and "invalid choice" in usage.stderr, broken.stdout + broken.stderr[-200:] + usage.stderr[-200:])

index_text = h.skills_index()
sizes = {p.parent.name: p.stat().st_size for p in (ROOT / "skills").glob("*/SKILL.md")}
delivery_skills = ("delivery-workflow", "feature-planning", "cloud-choice", "adr", "github-actions", "sonarqube",
                   "coding-conventions")
check("the delivery skills are indexed with one-line descriptions and stay small",
      all(f"- {name}: " in index_text for name in delivery_skills) and max(sizes.values()) < 4500
      and all(h.load_skill(name).startswith("---\nname: " + name) for name in delivery_skills), str(sizes))
check("no malformed requests sent", not mock_llm.ERRORS, "; ".join(mock_llm.ERRORS))

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
server.shutdown()
sys.exit(1 if failed else 0)
