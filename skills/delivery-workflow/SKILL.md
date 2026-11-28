---
name: delivery-workflow
description: How a delivery stage works, what the gate checks and which tools to use; load first in the build, pipeline and quality stages.
---

# Delivery workflow

You are one stage of a delivery pipeline. A person reviews what you produce; code, not
the model, decides whether the stage is accepted.

## Order of work
1. If .agent/gate-report.md exists, read it before anything else. It lists what the gate
   rejected last time, with the output of each failing check. Fix those problems first.
2. Read docs/plan/features.md and work only on the features marked "this run".
3. Save a checklist with update_plan: one line per feature, then tests, ADR, pr.md, commit.
4. Implement one feature at a time: read the file, change it, run the checks, repeat.
5. Record decisions as ADRs (load the adr skill) and write .agent/pr.md.
6. Commit with git_commit. The gate then runs the checks again on its own.

## Tools
- run_checks(name, reason) runs a command the operator approved: tests, lint and others
  named in the task. It needs no approval and may be repeated after every fix.
- run_shell runs only read-only commands (ls, cat, head, tail, grep, wc, pwd, diff)
  without an approval; anything else waits for a person and is usually refused. Never
  use it for tests, git, gh, pip, npm or installs.
- git_commit(branch, message) commits everything in the workspace to the feature branch.
  It refuses protected branches and leaves .agent/ out. Call it again after more changes.
- write_file and edit_file need no approval. edit_file needs the exact text you saw.

## What the gate checks
- Every configured check exits 0 (tests, lint, and in later stages actionlint or sonar).
- ADRs pass the lint (adr skill), and stages that must record a decision changed one.
- HEAD is on the feature branch, at least one commit ahead of the base branch, and the
  work tree has no uncommitted change outside .agent/.
A rejected stage is retried at a higher effort with an empty memory: only the files in
the workspace, the committed code and .agent/gate-report.md carry over. Leave the
workspace in a state your successor can continue from.

## Size limits that shape the work
- A file you read comes back clipped after 6000 characters, so keep every file under
  about 150 lines and split modules early.
- One write_file must fit in one reply: write one file at a time.
- Finish one feature completely (code, test, green check, commit) before the next.

## .agent/pr.md
First line: the pull request title. Then: what changed and why, how it was tested
(which checks passed), decisions recorded (ADR numbers), open items for the reviewer.

## Never
- Change docs/plan.md or the operator's configuration. Under .agent/ write only
  .agent/pr.md; update_plan keeps your checklist there for you.
- Leave files a check produced (coverage reports, scanner folders) unignored: the gate
  refuses an uncommitted tree, and generated files do not belong in a commit. If the
  repository has no .gitignore entry for them, add one.
- Put a credential, token or key in any file. Secrets are referenced by name only.
- Weaken or delete a failing test to make a check pass; fix the code or report why.
