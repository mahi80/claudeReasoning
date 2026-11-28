"""delivery_tools.py - guarded delivery tools: pre-approved checks, local commits, one push.

An operator-owned JSON file (AGENT_DELIVERY_CONFIG, kept outside the workspace) pins
what the agent may run. harness/delivery.example.json shows every field:

    checks       name -> {argv, timeout, env}: commands the model may run with run_checks
    gate         check names the build and quality gates run (deliver.py)
    stage_gates  per-stage override of that list, for example {"pipeline": ["actionlint"]}
    git          the operator's git dir, remote, base branch, protected patterns, author,
                 the name of the token variable, the GitHub repository for pull requests
                 and `config`, git settings passed on the command line (a proxy, say)
    adr          folder of decision records and the stages that must add or change one
    home         a private folder: HOME for every check under home/checks, the harness's
                 own git state under home/git (default: a folder next to the config)

What keeps the model away from credentials and from code execution through git:
- checks run with PATH and a private HOME, nothing from the operator's session, and
  every name under a check's `env` must be exported by the operator;
- git runs against the operator's git dir with system and global configuration disabled
  (an empty global file rewritten before every call), hooks pointed at a folder that
  does not exist, and command-line settings that pin protocol, redirects, proxy, ignore
  and attribute files; before every call the configuration git would read is scanned,
  and a push, redirect or code-running key from any file refuses the operation;
- the push goes to the configured URL only (a rewritten URL, a remote named by a URL
  and any push URL are refused), the token reaches git only through
  harness/git_credential.py, which answers for that host over https alone, and
  git_push_pr is the only tool that needs an approval click.
Checks still run as the same user as the harness: on a host that is not disposable,
run them under another user or in a container. See harness/deliver.py for the stages.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mini_harness import REGISTRY, WORKSPACE, Tool, inside_workspace, obj, time_left, trace

STAGES = ("plan", "platform", "build", "pipeline", "quality")
CHECK_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BRANCH_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
AUTHOR = re.compile(r"(.+?)\s*<([^<>\s]+@[^<>\s]+)>")
CONFIG_KEY = re.compile(r"[A-Za-z][A-Za-z0-9-]*\.(?:[^\s=]+\.)?[A-Za-z][A-Za-z0-9-]*")
HERE = Path(__file__).resolve().parent
HELPER = HERE / "git_credential.py"
NEVER_COMMITTED = (".agent", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
                   ".hypothesis", ".scannerwork", "htmlcov", "node_modules", ".venv")
NEVER_COMMITTED_FILES = (".coverage", ".coverage.*", "coverage.xml")
# Settings from a file that could redirect a push, change what git trusts or run a program.
UNSAFE_CONFIG = re.compile(
    r"^(url\..*\.(insteadof|pushinsteadof)|https?\..*|core\.(sshcommand|gitproxy|hookspath|fsmonitor"
    r"|fsmonitorhookversion|excludesfile|attributesfile|askpass|alternaterefscommand|pager|editor)"
    r"|credential\..*|include\.path|includeif\..*|filter\..*|diff\..*\.(command|textconv)"
    r"|merge\..*\.driver|alias\..*|uploadpack\..*|receive\..*|remote\..*\.(proxy|vcs|uploadpack"
    r"|receivepack)|gpg\..*|protocol\..*|ssh\..*)$", re.IGNORECASE)
DEFAULT_TIMEOUT, MAX_TIMEOUT = 120.0, 3600.0


class UnsafeConfig(RuntimeError):
    """git would read a setting the delivery tools refuse to run with."""


@dataclass(frozen=True)
class Check:
    name: str
    argv: tuple[str, ...]
    timeout: float
    env: tuple[str, ...]           # variable names copied from the operator's environment


@dataclass(frozen=True)
class Git:
    git_dir: Path
    remote: str                    # https URL, or a local directory for dry runs
    base: str
    protected: tuple[str, ...]     # fnmatch patterns; the base branch is always protected
    author_name: str
    author_email: str
    token_env: str
    repo: str                      # owner/name on GitHub; empty: push only, no pull request
    api: str
    config: tuple[tuple[str, str], ...] = ()   # operator settings passed as -c key=value


@dataclass(frozen=True)
class Config:
    source: Path
    home: Path
    checks: dict[str, Check]
    gate: tuple[str, ...]
    stage_gates: dict[str, tuple[str, ...]]
    git: Git | None
    adr_dir: str
    adr_required: tuple[str, ...]  # stages that must add or change a decision record

    def checks_for(self, stage: str) -> tuple[str, ...]:
        """Which configured checks the gate of this stage runs."""
        default = self.gate if stage in ("build", "quality") else ()
        return self.stage_gates.get(stage, default)


CONFIG: Config | None = None


# ---------------------------------------------------------------- configuration
def outside_workspace(path: Path, what: str) -> Path:
    path = path.resolve()
    if path == WORKSPACE or WORKSPACE in path.parents:
        raise ValueError(f"{what} must be outside the workspace: {path}")
    return path


def _check(name: str, spec) -> Check:
    if not CHECK_NAME.fullmatch(name) or not isinstance(spec, dict) or set(spec) - {"argv", "timeout", "env"}:
        raise ValueError(f"check '{name}' must be a lowercase name with argv, timeout and env only")
    argv, timeout, env = spec.get("argv"), spec.get("timeout", DEFAULT_TIMEOUT), spec.get("env", [])
    if (not isinstance(argv, list) or not argv
            or any(not isinstance(a, str) or not a for a in argv)):
        raise ValueError(f"check '{name}' needs argv: a non-empty list of strings")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError(f"check '{name}' timeout must be a number of seconds from 1 to {MAX_TIMEOUT:.0f}")
    if (not isinstance(env, list) or len(set(env)) != len(env)
            or any(not isinstance(n, str) or not ENV_NAME.fullmatch(n) for n in env)):
        raise ValueError(f"check '{name}' env must list distinct environment variable names")
    return Check(name, tuple(argv), float(timeout), tuple(env))


def _names(value, checks: dict[str, Check], what: str) -> tuple[str, ...]:
    if (not isinstance(value, list) or len(set(value)) != len(value)
            or any(not isinstance(n, str) or n not in checks for n in value)):
        raise ValueError(f"{what} must list distinct configured check names")
    return tuple(value)


def _git(spec) -> Git:
    keys = {"git_dir", "remote", "base", "protected", "author", "token_env", "repo", "api", "config"}
    if not isinstance(spec, dict) or set(spec) - keys or "git_dir" not in spec or "remote" not in spec:
        raise ValueError("git block needs git_dir and remote; other keys: base, protected, author, "
                         "token_env, repo, api, config")
    git_dir = outside_workspace(Path(str(spec["git_dir"])), "git_dir")
    if not (git_dir / "HEAD").is_file():
        raise ValueError(f"git_dir {git_dir} is not a git directory (clone with --separate-git-dir)")
    remote = spec["remote"]
    local = isinstance(remote, str) and Path(remote).is_dir()
    parsed = urlparse(remote) if isinstance(remote, str) else None
    if not isinstance(remote, str) or not (local or (parsed.scheme == "https" and parsed.netloc)):
        raise ValueError("remote must be an https URL or an existing local directory")
    if not local and (parsed.username or parsed.password):
        raise ValueError("remote must not embed credentials; the token comes from token_env")
    if local:
        remote = str(outside_workspace(Path(remote), "a local remote"))
    base = spec.get("base", "main")
    if not isinstance(base, str) or not BRANCH_NAME.fullmatch(base):
        raise ValueError("base must be a branch name")
    protected = spec.get("protected", ["main", "master"])
    if not isinstance(protected, list) or any(not isinstance(p, str) or not p for p in protected):
        raise ValueError("protected must be a list of branch patterns")
    author = AUTHOR.fullmatch(str(spec.get("author", "Delivery Agent <delivery-agent@example.invalid>")))
    if not author:
        raise ValueError("author must look like 'Name <email>'")
    token_env = spec.get("token_env", "GH_TOKEN")
    if not isinstance(token_env, str) or not ENV_NAME.fullmatch(token_env):
        raise ValueError("token_env must be an environment variable name")
    repo = spec.get("repo", "")
    if not isinstance(repo, str) or (repo and not REPO_NAME.fullmatch(repo)):
        raise ValueError("repo must be owner/name")
    api = spec.get("api", "https://api.github.com")
    if not isinstance(api, str) or urlparse(api).scheme != "https" or not urlparse(api).netloc:
        raise ValueError("api must be an https URL")
    settings = spec.get("config", {})
    if (not isinstance(settings, dict) or any(
            not isinstance(k, str) or not CONFIG_KEY.fullmatch(k) or not isinstance(v, str)
            or re.search(r"[\r\n\x00]", v) for k, v in settings.items())):
        raise ValueError("git config must map git setting names to single-line string values")
    return Git(git_dir, remote, base, tuple(dict.fromkeys([base, *protected])), author.group(1).strip(),
               author.group(2), token_env, repo, api.rstrip("/"), tuple(settings.items()))


def load_config(path: str) -> Config:
    """Validate the operator's delivery config. Every problem is an error, never a default."""
    source = outside_workspace(Path(path), "the delivery config")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) - {"home", "checks", "gate", "stage_gates", "git", "adr"}:
        raise ValueError("delivery config must be an object with only home, checks, gate, "
                         "stage_gates, git and adr")
    home = outside_workspace(Path(str(raw.get("home", source.parent / "home"))), "home")
    if not isinstance(raw.get("checks", {}), dict):
        raise ValueError("checks must be an object of name -> {argv, timeout, env}")
    checks = {name: _check(name, spec) for name, spec in raw.get("checks", {}).items()}
    gate = _names(raw.get("gate", []), checks, "gate")
    stage_gates = raw.get("stage_gates", {})
    if not isinstance(stage_gates, dict) or set(stage_gates) - set(STAGES):
        raise ValueError(f"stage_gates keys must be stages: {', '.join(STAGES)}")
    stage_gates = {stage: _names(names, checks, f"stage_gates.{stage}") for stage, names in stage_gates.items()}
    git = _git(raw["git"]) if "git" in raw else None
    adr = raw.get("adr", {})
    if not isinstance(adr, dict) or set(adr) - {"dir", "require_changed"}:
        raise ValueError("adr block takes dir and require_changed only")
    adr_dir = adr.get("dir", "docs/adr")
    if (not isinstance(adr_dir, str) or not adr_dir or Path(adr_dir).is_absolute()
            or ".." in Path(adr_dir).parts):
        raise ValueError("adr dir must be a relative path inside the workspace")
    required = adr.get("require_changed", ["platform", "pipeline", "quality"])
    if not isinstance(required, list) or set(required) - set(STAGES):
        raise ValueError("adr require_changed must list stages")
    return Config(source, home, checks, gate, stage_gates, git, adr_dir, tuple(required))


def required() -> Config:
    if CONFIG is None:
        raise RuntimeError("delivery tools are not configured; call register() first")
    return CONFIG


# ---------------------------------------------------------------- running commands
def checks_home(config: Config) -> Path:
    return config.home / "checks"


def git_state(config: Config) -> Path:
    """The harness's own git state: never the HOME of a check process."""
    return config.home / "git"


def _env(home: Path) -> dict[str, str]:
    """PATH, the given HOME and a temp folder under it; nothing else from the operator's session."""
    tmp = home / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home),
           "TMPDIR": str(tmp), "TEMP": str(tmp), "TMP": str(tmp)}
    if os.name == "nt":                            # Windows programs need these to start
        env.update({name: os.environ[name] for name in
                    ("SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR") if name in os.environ})
    return env


def base_env(config: Config) -> dict[str, str]:
    return _env(checks_home(config))


def check_env(config: Config, check: Check) -> dict[str, str]:
    env = base_env(config)
    env.update({name: os.environ[name] for name in check.env if name in os.environ})
    return env


def _text(value) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")


def run_check(config: Config, check: Check, timeout: float | None = None) -> tuple[int | None, str, float]:
    """Run one pre-approved command in the workspace: (exit code or None, output, seconds)."""
    started, limit = time.monotonic(), check.timeout if timeout is None else timeout
    missing = [name for name in check.env if name not in os.environ]
    if missing:                                    # a token the operator has not exported here
        trace("check", name=check.name, exit=None, seconds=0)
        return None, (f"cannot run {check.name}: {', '.join(missing)} is not set in the harness "
                      "environment; the operator must export it"), 0.0
    try:
        done = subprocess.run(list(check.argv), cwd=WORKSPACE, env=check_env(config, check),
                              capture_output=True, text=True, errors="replace", timeout=limit)
        code, output = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as err:
        code = None
        output = f"{_text(err.stdout)}{_text(err.stderr)}\n(stopped: no result after {limit:.0f} seconds)"
    except OSError as err:
        code, output = None, f"cannot start {check.argv[0]}: {err}"
    seconds = time.monotonic() - started
    trace("check", name=check.name, exit=code, seconds=round(seconds, 1))
    return code, output, seconds


# ---------------------------------------------------------------- git
def git_env(config: Config) -> dict[str, str]:
    """git reads no system file, an empty global file rewritten now, and nothing under a check's HOME."""
    state = git_state(config)
    env = _env(state)
    empty = state / "gitconfig"
    empty.write_bytes(b"")
    env.update(XDG_CONFIG_HOME=str(state), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(empty),
               GIT_TERMINAL_PROMPT="0")
    return env


def hardening(config: Config) -> list[str]:
    """Command-line settings that win over every file: no hooks, no rewrites, https only."""
    git, state = config.git, git_state(config)
    empty, local = state / "gitconfig", not config.git.remote.startswith("https://")
    flags = ["-c", f"core.hooksPath={state / ('no-hooks-' + uuid.uuid4().hex)}",   # never exists
             "-c", "core.fsmonitor=",             # empty: unset on old git, false on new git
             "-c", f"core.excludesFile={empty}", "-c", f"core.attributesFile={empty}",
             "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "gc.auto=0",
             "-c", "protocol.allow=never", "-c", f"protocol.{'file' if local else 'https'}.allow=always",
             "-c", "http.followRedirects=false", "-c", "http.proxy=", "-c", "http.sslVerify=true",
             "-c", "push.recurseSubmodules=no", "-c", "submodule.recurse=false",
             "-c", f"user.name={git.author_name}", "-c", f"user.email={git.author_email}"]
    for key, value in git.config:                  # the operator's own settings, trusted
        flags += ["-c", f"{key}={value}"]
    return flags


def run_git(config: Config, args: list[str], timeout: float = 60,
            extra_env: dict[str, str] | None = None, scan: bool = True) -> subprocess.CompletedProcess:
    """git against the operator's git dir and the workspace. Refuses unsafe file settings first."""
    if scan:
        problems = config_problems(config, timeout)
        if problems:
            raise UnsafeConfig("; ".join(problems))
    command = ["git", f"--git-dir={config.git.git_dir}", f"--work-tree={WORKSPACE}", *hardening(config), *args]
    env = git_env(config)
    env.update(extra_env or {})
    return subprocess.run(command, cwd=WORKSPACE, env=env, capture_output=True, text=True,
                          errors="replace", timeout=timeout)


def config_problems(config: Config, timeout: float = 60) -> list[str]:
    """Settings git would read from a file that could redirect a push or run a program."""
    listing = run_git(config, ["config", "--list", "--show-origin", "--name-only"], timeout, scan=False)
    if listing.returncode:
        return [f"git configuration could not be read: {listing.stderr.strip()}"]
    problems = []
    for line in listing.stdout.splitlines():
        origin, _, key = line.partition("\t")
        if origin.startswith("command line") or not (UNSAFE_CONFIG.match(key) or _unsafe_remote(config, key)):
            continue
        problems.append(f"git setting {key} in {origin} could redirect a push or run a program; "
                        "remove it, or put it in the delivery config under git.config")
    return problems


def _unsafe_remote(config: Config, key: str) -> bool:
    """A remote named by a URL, or any push URL: `git push <url>` would follow them instead."""
    section, _, rest = key.partition(".")
    if section.lower() != "remote" or "." not in rest:
        return False
    name, _, setting = rest.rpartition(".")
    return setting.lower() == "pushurl" or "/" in name or ":" in name or name == config.git.remote


def excludes() -> list[str]:
    """Pathspecs that keep agent state, caches and check reports out of commits and status."""
    return ([f":(glob,exclude)**/{name}/**" for name in NEVER_COMMITTED]
            + [f":(glob,exclude)**/{name}" for name in NEVER_COMMITTED_FILES])


def branch_problem(config: Config, branch: str) -> str:
    if (not BRANCH_NAME.fullmatch(branch) or ".." in branch or "//" in branch or "@{" in branch
            or branch.endswith(("/", ".", ".lock"))
            or any(part.startswith(".") for part in branch.split("/"))):
        return f"ERROR: '{branch}' is not a valid branch name"
    if any(fnmatch.fnmatchcase(branch, pattern) for pattern in config.git.protected):
        return f"ERROR: '{branch}' is protected; work on a feature branch such as feature/<slug>"
    return ""


def base_ref(config: Config, timeout: float = 60) -> str | None:
    for ref in (config.git.base, f"origin/{config.git.base}"):
        if run_git(config, ["rev-parse", "--verify", "--quiet", ref], timeout=timeout).returncode == 0:
            return ref
    return None


def head_commit(config: Config, timeout: float = 60) -> str | None:
    head = run_git(config, ["rev-parse", "--verify", "--quiet", "HEAD"], timeout=timeout)
    return head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else None


def changed_paths(config: Config, subdir: str, since: str | None = None, timeout: float = 60) -> list[str] | None:
    """Files under subdir that differ from `since` (default: the base branch), committed or not."""
    since = since or base_ref(config, timeout)
    if since is None:
        return None
    diff = run_git(config, ["diff", "--name-only", since, "--", subdir, *excludes()], timeout=timeout)
    new = run_git(config, ["ls-files", "--others", "--exclude-standard", "--", subdir, *excludes()],
                  timeout=timeout)
    if diff.returncode or new.returncode:
        return None
    return sorted(set(diff.stdout.split() + new.stdout.split()))


def tree_status(config: Config, timeout: float = 60) -> list[str] | None:
    """Paths that differ from HEAD or are untracked, minus the excludes; None if git failed."""
    status = run_git(config, ["status", "--porcelain", "--untracked-files=all", "--", ".", *excludes()],
                     timeout=timeout)
    if status.returncode:
        return None
    return sorted(line[3:] for line in status.stdout.splitlines() if line.strip())


def agent_changes(config: Config, subdir: str, since: str, timeout: float = 60) -> list[str] | None:
    """Files under subdir the agent changed since a commit: in its own commits, or still uncommitted.

    Commits by anyone else (a merge, a rebase, a person accepting a record) do not count,
    so a stage cannot satisfy a 'record your decision' rule with someone else's work.
    """
    commits = run_git(config, ["rev-list", f"--author={config.git.author_email}", f"{since}..HEAD"],
                      timeout=timeout)
    if commits.returncode:
        return None
    paths: set[str] = set()
    for sha in commits.stdout.split():
        tree = run_git(config, ["diff-tree", "--no-commit-id", "--name-only", "-r", sha, "--", subdir,
                                *excludes()], timeout=timeout)
        if tree.returncode:
            return None
        paths.update(tree.stdout.split())
    pending = run_git(config, ["diff", "--name-only", "HEAD", "--", subdir, *excludes()], timeout=timeout)
    new = run_git(config, ["ls-files", "--others", "--exclude-standard", "--", subdir, *excludes()],
                  timeout=timeout)
    if pending.returncode or new.returncode:
        return None
    return sorted(paths | set(pending.stdout.split()) | set(new.stdout.split()))


def git_problems(config: Config, branch: str, timeout: float = 60) -> list[str]:
    """Why the work tree is not ready for a pull request: wrong branch, no commit, dirty tree."""
    try:
        head = run_git(config, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=timeout)
    except UnsafeConfig as err:
        return [str(err)]
    problems = []
    current = head.stdout.strip()
    if head.returncode or current != branch:
        problems.append(f"HEAD is on '{current or '?'}' instead of {branch}; "
                        f'commit with git_commit(branch="{branch}", ...)')
    base = base_ref(config, timeout)
    if base is None:
        problems.append(f"base branch {config.git.base} was not found locally")
    else:
        ahead = run_git(config, ["rev-list", "--count", f"{base}..HEAD"], timeout=timeout)
        if ahead.returncode or ahead.stdout.strip() == "0":
            problems.append(f"no commits ahead of {base}; commit the work with git_commit")
    status = run_git(config, ["status", "--porcelain", "--untracked-files=all", "--", ".", *excludes()],
                     timeout=timeout)
    if status.returncode:
        problems.append(f"git status failed: {status.stderr.strip()}")
    elif status.stdout.strip():
        files = [line[3:] for line in status.stdout.splitlines()]
        problems.append("uncommitted changes: " + ", ".join(files[:20])
                        + (" ..." if len(files) > 20 else "") + "; run git_commit")
    return problems


def redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


# ---------------------------------------------------------------- the tools
def run_checks(name: str, reason: str) -> str:
    config = required()
    check = config.checks.get(name)
    if check is None:
        return (f"ERROR: no check named '{name}'. Configured checks: "
                f"{', '.join(sorted(config.checks)) or 'none'}")
    code, output, seconds = run_check(config, check, timeout=time_left(check.timeout))
    time_left(check.timeout)
    return f"exit={'none' if code is None else code} after {seconds:.0f}s\n{output}"


def git_commit(branch: str, message: str) -> str:
    config = required()
    problem = branch_problem(config, branch)
    if problem:
        return problem
    message = message.strip()
    if not message:
        return "ERROR: a commit message is required"
    try:
        return _commit(config, branch, message)
    except UnsafeConfig as err:
        return f"ERROR: git configuration refused: {err}"


def _commit(config: Config, branch: str, message: str) -> str:
    head = run_git(config, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=time_left(60))
    current = head.stdout.strip() if head.returncode == 0 else ""
    if current != branch:
        exists = run_git(config, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                         timeout=time_left(60))
        if exists.returncode == 0:
            return (f"ERROR: branch {branch} exists but '{current or 'a detached HEAD'}' is checked "
                    f"out; commit on {current} or ask the operator to switch branches")
        made = run_git(config, ["checkout", "-q", "-b", branch], timeout=time_left(60))
        if made.returncode:
            return f"ERROR: could not create branch {branch}:\n{made.stderr.strip()}"
    added = run_git(config, ["add", "-A", "--", ".", *excludes()], timeout=time_left(120))
    if added.returncode:
        return f"ERROR: git add failed:\n{added.stderr.strip()}"
    if run_git(config, ["diff", "--cached", "--quiet"], timeout=time_left(60)).returncode == 0:
        return f"nothing to commit on {branch}: every change is already committed"
    done = run_git(config, ["commit", "-q", "--no-verify", "-m", message,
                            f"--author={config.git.author_name} <{config.git.author_email}>"],
                   timeout=time_left(60))
    if done.returncode:
        return f"ERROR: commit failed:\n{(done.stdout + done.stderr).strip()}"
    shown = run_git(config, ["show", "--stat", "--format=%h %s", "HEAD"], timeout=time_left(60))
    trace("commit", branch=branch, commit=shown.stdout.split()[0] if shown.stdout.split() else "")
    return f"committed on {branch}:\n{shown.stdout.strip()}"


def open_pull_request(git: Git, token: str, branch: str, title: str, body: str) -> str:
    import httpx                       # a declared dependency, imported late to keep startup light
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "mini-harness-delivery"}
    owner = git.repo.split("/")[0]
    with httpx.Client(timeout=30, headers=headers) as http:
        created = http.post(f"{git.api}/repos/{git.repo}/pulls",
                            json={"title": title, "head": branch, "base": git.base, "body": body})
        if created.status_code == 422:             # most often: the pull request already exists
            found = http.get(f"{git.api}/repos/{git.repo}/pulls",
                             params={"head": f"{owner}:{branch}", "state": "open"})
            if found.status_code == 200 and found.json():
                return found.json()[0]["html_url"]
        if created.status_code >= 400:
            raise RuntimeError(f"GitHub answered {created.status_code}: {created.text[:300]}")
        return created.json()["html_url"]


def credential_helper() -> str:
    """The git credential.helper value: our script, run without site packages, quoted for sh."""
    return "!" + " ".join(shlex.quote(part) for part in
                          (Path(sys.executable).as_posix(), "-I", "-S", HELPER.as_posix()))


def git_push_pr(branch: str, title: str, body_path: str) -> str:
    config = required()
    git = config.git
    problem = branch_problem(config, branch)
    if problem:
        return problem
    title = title.strip()
    if not title:
        return "ERROR: a pull request title is required"
    body = ""
    if body_path.strip():
        try:
            body = inside_workspace(body_path).read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as err:
            return f"ERROR: cannot read {body_path}: {err}"
    over_https = git.remote.startswith("https://")
    token = os.environ.get(git.token_env, "") if over_https else ""
    if over_https and not token:
        return (f"ERROR: {git.token_env} is not set in the harness environment; "
                "the operator must export it before a push")
    try:
        return _push(config, branch, title, body, token)
    except UnsafeConfig as err:
        return f"ERROR: git configuration refused: {redact(str(err), token)}"
    except (subprocess.TimeoutExpired, OSError) as err:
        return f"ERROR: push failed: {redact(str(err), token)}"


def _push(config: Config, branch: str, title: str, body: str, token: str) -> str:
    git = config.git
    exists = run_git(config, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                     timeout=time_left(60))
    if exists.returncode:
        return f"ERROR: there is no local branch {branch}; commit first with git_commit"
    effective = run_git(config, ["ls-remote", "--get-url", git.remote], timeout=time_left(60))
    target = effective.stdout.strip()
    same = target == git.remote or (not git.remote.startswith("https://") and target
                                    and Path(target).resolve() == Path(git.remote).resolve())
    if effective.returncode or not same:
        return (f"ERROR: git would push to '{redact(target, token)}' instead of the configured remote; "
                "refusing. Check the repository's git configuration for url rewrites")
    host = urlparse(git.remote).netloc if git.remote.startswith("https://") else ""
    pushed = run_git(config, ["-c", "credential.helper=", "-c", f"credential.helper={credential_helper()}",
                              "push", "--no-verify", "--", git.remote,
                              f"refs/heads/{branch}:refs/heads/{branch}"],
                     timeout=time_left(300), extra_env={"DELIVERY_TOKEN": token, "DELIVERY_HOST": host})
    if pushed.returncode:
        return (f"ERROR: push failed (exit {pushed.returncode}):\n"
                f"{redact(pushed.stdout + pushed.stderr, token).strip()}")
    trace("push", branch=branch, remote=git.remote)
    if not git.repo:
        return (f"pushed {branch} to {git.remote}; no GitHub repository is configured, "
                "so open the pull request by hand")
    try:
        url = open_pull_request(git, token, branch, title, body)
    except Exception as err:
        return f"pushed {branch}, but the pull request could not be opened: {redact(str(err), token)}"
    trace("pull_request", branch=branch, url=url)
    return f"pushed {branch} and opened the pull request: {url}"


# ---------------------------------------------------------------- registration
def register(path: str, adr_lint: Path | None = None) -> list[str]:
    """Load the operator's config and add the delivery tools to the registry. Returns names.

    With adr_lint, a check named "adr" that lints the decision records is added unless
    the operator configured one, so the model can lint before the gate does. The harness,
    the interpreter and the helper must live outside the workspace: the model can write
    any file there, and these run with the token.
    """
    global CONFIG
    config = load_config(path)
    for what, where in (("the harness", HERE), ("the interpreter", Path(sys.executable)),
                        ("the credential helper", HELPER)) + ((("the ADR lint", adr_lint),) if adr_lint else ()):
        outside_workspace(where, what)
    if adr_lint is not None and "adr" not in config.checks:
        config.checks["adr"] = Check("adr", (sys.executable, "-I", str(adr_lint), config.adr_dir), 60.0, ())
    names = ", ".join(sorted(config.checks)) or "none configured"
    tools = [Tool(
        "run_checks", "Run one of the operator's pre-approved checks in the workspace and return "
        f"its exit code and output. Configured checks: {names}. Use it for tests and linters "
        "instead of run_shell; it needs no approval and may be repeated after each fix.",
        obj(name="Check name exactly as configured",
            reason="Why you run it now, in a few words"), run_checks, repeatable=True)]
    if config.git:
        tools += [Tool(
            "git_commit", "Commit every change in the workspace to the named feature branch, "
            "creating the branch from the current head when it does not exist. Protected "
            "branches are refused and nothing under .agent/ is committed. Call it when the "
            "checks pass, and again after further changes.",
            obj(branch="Branch name, for example feature/<slug>",
                message="Commit message: a short subject line, then why"), git_commit), Tool(
            "git_push_pr", "Push one committed feature branch to the configured remote and open "
            "a pull request against the base branch. The operator must approve it. Use it once, "
            "when the work is committed and the checks pass.",
            obj(branch="The branch to push", title="Pull request title",
                body_path="Workspace file holding the pull request body, for example .agent/pr.md"),
            git_push_pr, needs_approval=True)]
    for t in tools:
        REGISTRY[t.name] = t
    CONFIG = config
    return [t.name for t in tools]


def close() -> None:
    global CONFIG
    for name in ("run_checks", "git_commit", "git_push_pr"):
        REGISTRY.pop(name, None)
    CONFIG = None
