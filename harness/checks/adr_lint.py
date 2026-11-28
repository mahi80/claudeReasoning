"""adr_lint.py - check architecture decision records against the house rules.

Usage: python adr_lint.py [DIR] [--index README.md]
                          [--base <branch or commit> [--author EMAIL] [--git-dir D] [--work-tree W]]

Rules (the adr skill tells the model the same):
  - files are NNNN-slug.md: four digits, then lowercase words joined by hyphens
  - numbers are unique and the first line is "# NNNN. Title" with the file's own number
  - a "Status:" line holds Proposed, Accepted, Rejected, Deprecated or "Superseded by NNNN"
  - a "Date:" line holds YYYY-MM-DD
  - the headings Context, Decision, Consequences, Alternatives considered and
    Assumptions to confirm are present, in that order
  - each record stays under 6000 bytes, so the agent can read it back unclipped
  - README.md in the folder names every record, and nothing that does not exist
  - with --base, at least one record under DIR was added or changed since that branch or
    commit (with --author, in that author's commits or still uncommitted)
Prints "OK: N records" and exits 0, or one problem per line and exits 1.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FILE = re.compile(r"(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
TITLE = re.compile(r"# (\d{4})\. \S.*")
STATUS = re.compile(r"Status: (Proposed|Accepted|Rejected|Deprecated|Superseded by \d{4})\s*")
DATE = re.compile(r"Date: \d{4}-\d{2}-\d{2}\s*")
HEADINGS = ("## Context", "## Decision", "## Consequences", "## Alternatives considered",
            "## Assumptions to confirm")
MAX_BYTES = 6000


def lint(folder: Path, index: str = "README.md", changed: list[str] | None = None,
         since: str = "the base branch") -> list[str]:
    """Every problem found, as 'file: problem' lines. Empty means the records are in order.

    `changed` lists the paths added or changed since `since`; when given, at least one
    record must be among them.
    """
    if not folder.is_dir():
        return [f"{folder}: folder not found"]
    problems, numbers = [], {}
    entries = sorted(p for p in folder.glob("*.md") if p.name != index)
    records = [p for p in entries if p.is_file()]
    problems += [f"{p.name}: must be a file, not a folder" for p in entries if not p.is_file()]
    for p in records:
        match = FILE.fullmatch(p.name)
        if not match:
            problems.append(f"{p.name}: file name must be NNNN-slug.md (four digits, then lowercase "
                            "words joined by hyphens)")
            continue
        number = match.group(1)
        if number in numbers:
            problems.append(f"{p.name}: number {number} is also used by {numbers[number]}")
        numbers[number] = p.name
        raw = p.read_bytes()
        if len(raw) > MAX_BYTES:
            problems.append(f"{p.name}: {len(raw)} bytes; keep a record under {MAX_BYTES}")
        lines = raw.decode("utf-8", errors="replace").splitlines()
        title = TITLE.fullmatch(lines[0].strip()) if lines else None
        if not title:
            problems.append(f"{p.name}: first line must be '# {number}. Title'")
        elif title.group(1) != number:
            problems.append(f"{p.name}: title number {title.group(1)} does not match the file name")
        if not any(STATUS.fullmatch(line) for line in lines):
            problems.append(f"{p.name}: needs a 'Status: ' line with Proposed, Accepted, Rejected, "
                            "Deprecated or Superseded by NNNN")
        if not any(DATE.fullmatch(line) for line in lines):
            problems.append(f"{p.name}: needs a 'Date: YYYY-MM-DD' line")
        positions = [next((i for i, line in enumerate(lines) if line.strip() == heading), None)
                     for heading in HEADINGS]
        missing = [h for h, pos in zip(HEADINGS, positions) if pos is None]
        if missing:
            problems.append(f"{p.name}: missing headings: {', '.join(missing)}")
        elif positions != sorted(positions):
            problems.append(f"{p.name}: headings out of order; use {', '.join(HEADINGS)}")
    listing = folder / index
    if records and not listing.is_file():
        problems.append(f"{index}: missing; list every record as [NNNN](NNNN-slug.md) and its title")
    elif listing.is_file():
        text = listing.read_text(encoding="utf-8", errors="replace")
        problems += [f"{index}: does not list {p.name}" for p in records if p.name not in text]
        problems += [f"{index}: names {name}, which does not exist"
                     for name in sorted(set(re.findall(r"\b(\d{4}-[a-z0-9-]+\.md)\b", text)))
                     if not (folder / name).is_file()]
    if changed is not None and not any(FILE.fullmatch(Path(c).name) for c in changed):
        problems.append(f"no record under {folder.name}/ was added or changed since {since}; "
                        "record the decision as an ADR")
    return problems


def changed_since(base: str, folder: str, git_dir: str = "", work_tree: str = "",
                  author: str = "") -> list[str]:
    """Files under folder that differ from base, committed or not (used standalone, with --base).

    With an author, only that author's commits since base count, plus uncommitted changes.
    git runs without system or global configuration, hooks or a file monitor, so a
    repository's own settings cannot make this read-only comparison run a program.
    """
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "gitconfig"
        empty.touch()
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
               "GIT_TERMINAL_PROMPT": "0"}
        git = (["git"] + ([f"--git-dir={git_dir}"] if git_dir else [])
               + ([f"--work-tree={work_tree}"] if work_tree else [])
               + ["-c", "core.fsmonitor=", "-c", f"core.hooksPath={Path(tmp) / 'no-hooks'}"])

        def run(*args: str) -> list[str]:
            done = subprocess.run(git + list(args), capture_output=True, text=True, timeout=60, env=env)
            if done.returncode:
                raise RuntimeError(done.stderr.strip() or "git failed")
            return done.stdout.split()

        if author:
            paths = set()
            for sha in run("rev-list", f"--author={author}", f"{base}..HEAD"):
                paths.update(run("diff-tree", "--no-commit-id", "--name-only", "-r", sha, "--", folder))
            paths.update(run("diff", "--name-only", "HEAD", "--", folder))
        else:
            paths = set(run("diff", "--name-only", base, "--", folder))
        paths.update(run("ls-files", "--others", "--exclude-standard", "--", folder))
    return sorted(paths)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Lint architecture decision records.")
    cli.add_argument("dir", nargs="?", default="docs/adr")
    cli.add_argument("--index", default="README.md")
    cli.add_argument("--base", default="", help="require a record added or changed since this branch or commit")
    cli.add_argument("--author", default="", help="with --base: count only this author's commits")
    cli.add_argument("--git-dir", default="")
    cli.add_argument("--work-tree", default="")
    args = cli.parse_args(argv)
    changed = None
    if args.base:
        try:
            changed = changed_since(args.base, args.dir, args.git_dir, args.work_tree, args.author)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as err:
            print(f"cannot compare with {args.base}: {err}")
            return 1
    problems = lint(Path(args.dir), args.index, changed, since=args.base[:12] if args.base else "the base branch")
    if problems:
        print("\n".join(problems))
        return 1
    count = sum(1 for p in Path(args.dir).glob("*.md") if p.name != args.index)
    print(f"OK: {count} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
