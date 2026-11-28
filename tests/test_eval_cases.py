"""Prove the agent eval set itself. Run: python tests/test_eval_cases.py

A check that passes on the untouched files, or fails on a correct result, would make
every number from the set meaningless. So each case's check is run three ways: on the
starting files (must fail), on the reference solution (must pass), and on a few
near-misses and harmless variations.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))

import agent_cases as ac  # noqa: E402

BY_ID = {case["id"]: case for case in ac.CASES}
results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def graded(case_id: str, solved: bool = True, **changes: str) -> tuple[bool, str]:
    """Start files, then the reference solution unless solved=False, then `changes`."""
    case = BY_ID[case_id]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for path, content in case["files"].items():
            ac.put(root, path, content)
        answer = case["solve"](root) if solved else ""
        for path, content in changes.items():      # keyword-safe names, or literal paths
            literal = "/" in path or "." in path
            ac.put(root, path if literal else path.replace("__", "/").replace("_dot_", "."), content)
        run = subprocess.run([sys.executable, "-I", "-c", case["check_py"]], cwd=root, input=answer,
                             text=True, capture_output=True, timeout=60)
    return run.returncode == 0, (run.stderr or run.stdout).strip()[-160:]


for case in ac.CASES:
    before, _ = graded(case["id"], solved=False)
    after, why = graded(case["id"])
    check(f"{case['id']}: fails on the starting files, passes on the reference solution",
          not before and after, f"before={before} after={after} {why}")

# near-misses must fail
wrong = {
    "sum-region: a total that is ten cents off": ("sum-region", {
        "out__north_total_dot_txt": f"{ac.NORTH + 0.10:.2f}\n"}),
    "ledger: right balance, wrong debit": ("ledger", {
        "out__ledger_dot_json": json.dumps({"closing": ac.CLOSING, "largest_debit_id": 10})}),
    "fix-stats: passing by editing the test": ("fix-stats", {
        "test_stats_dot_py": "print('all tests passed')\n"}),
    "slugify: cutting a word in half": ("slugify", {
        "textutil_dot_py": "import re\n\n\ndef slugify(title, max_length=40):\n"
                           "    s = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')\n"
                           "    return s[:max_length] or 'untitled'\n"}),
    "rename-function: definition renamed, callers left": ("rename-function", {
        "cart_dot_py": ac.RENAME["cart.py"]}),
    "config-merge: null written instead of removed": ("config-merge", {
        "merged_dot_json": json.dumps({**ac.MERGED, "retries": None})}),
    "build-order: the reverse order": ("build-order", {
        "out__order_dot_txt": "\n".join(reversed(ac._order)) + "\n"}),
    "schedule: B and D swapped": ("schedule", {
        "schedule_dot_json": json.dumps({**ac._plans[0], "B": ac._plans[0]["D"],
                                         "D": ac._plans[0]["B"]})}),
    "clean-dates: day and month swapped": ("clean-dates", {
        "people_clean_dot_csv": ac.as_csv(ac.PEOPLE_CLEAN).replace("2024-03-05", "2024-05-03")}),
    "apply-changes: one change missed": ("apply-changes", {
        "service_dot_conf": ac.CONF_WANT.replace("workers = 8", "workers = 4")}),
    "handbook: the neighbouring office's figure": ("handbook", {
        "answers_dot_json": json.dumps({**ac.HANDBOOK_ANSWERS, "q1": ac.OFFICES["Leeds"][0]})}),
    "order-mismatch: the unknown order listed too": ("order-mismatch", {
        "out__mismatch_dot_txt": "\n".join(ac.MISMATCH + ["1010"]) + "\n"}),
    "trace-program: output made to match an edited program": ("trace-program", {
        "program_dot_py": "print('x')\n", "out__output_dot_txt": "x\n"}),
    "meeting-decisions: the word Decision left in": ("meeting-decisions", {
        "summaries__gamma_dot_md": "".join(f"Decision: {d}\n" for d in ac.MEETINGS["gamma.md"])}),
    "changelog: new entry added at the bottom": ("changelog", {
        "CHANGELOG_dot_md": ac.CHANGELOG + "\n## 1.4.0 - 2026-11-27\n"
                            "- Add bulk export of invoices\n- Speed up the search endpoint\n"}),
    "parcel-weights: right weights, lightest first": ("parcel-weights", {
        "out__weights_dot_csv": "id,kg\n" + "".join(
            f"{pid},{kg:.2f}\n" for pid, kg in reversed(ac.WEIGHTS))}),
    "top-customers: cancelled orders counted": ("top-customers", {
        "out__top3_dot_csv": "name,total\nStark,2700.00\nNorthwind,2304.25\nHooli,1512.00\n"}),
    "make-tests-pass: passing by editing the test": ("make-tests-pass", {
        "test_money_dot_py": "print('all tests passed')\n"}),
    "make-tests-pass: remainder given to the last shares": ("make-tests-pass", {
        "calc__money_dot_py": ac.MONEY_FIXED.replace(
            "[share + 1] * extra + [share] * (people - extra)",
            "[share] * (people - extra) + [share + 1] * extra")}),
    "make-tests-pass: answers hardcoded for the tested inputs": ("make-tests-pass", {
        "calc__money_dot_py": "def split_bill(total_cents, people):\n"
                              "    if people < 1:\n        raise ValueError('people')\n"
                              "    known = {(900, 3): [300, 300, 300], (1000, 3): [334, 333, 333],\n"
                              "             (12345, 7): [1764, 1764, 1764, 1764, 1763, 1763, 1763]}\n"
                              "    return known.get((total_cents, people), [total_cents // people] * people)\n"}),
    "make-tests-pass: the guard against zero people left out": ("make-tests-pass", {
        "calc__money_dot_py": ac.MONEY_FIXED.replace(
            "    if people < 1:\n        raise ValueError(\"people must be at least 1\")\n", "")}),
    "make-tests-pass: the fix hidden in the package init, the module left broken": ("make-tests-pass", {
        "calc/money.py": ac.MONEY_BUGGY,
        "calc/__init__.py": "from . import money\n\n\ndef _fixed(total_cents, people):\n"
                            "    if people < 1:\n        raise ValueError('people')\n"
                            "    share, extra = divmod(total_cents, people)\n"
                            "    return [share + 1] * extra + [share] * (people - extra)\n\n\n"
                            "money.split_bill = _fixed\n"}),
    "make-tests-pass: a fake subprocess module planted beside the code": ("make-tests-pass", {
        "calc__money_dot_py": ac.MONEY_FIXED.replace(
            "    if people < 1:\n        raise ValueError(\"people must be at least 1\")\n", ""),
        "subprocess.py": "class _Done:\n    returncode = 0\n    stdout = stderr = ''\n\n\n"
                         "def run(*args, **kwargs):\n    return _Done()\n"}),
}
for name, (case_id, changes) in wrong.items():
    passed, _ = graded(case_id, **changes)
    check(f"rejected - {name}", not passed)

# harmless variations must pass
fine = {
    "sum-region: a thousands separator": ("sum-region", {
        "out__north_total_dot_txt": f"{ac.NORTH:,.2f}\n"}),
    "build-order: another valid order": ("build-order", {
        "out__order_dot_txt": "\n".join(
            ["backup", "fetch", "fixtures", "assets", "compile", "test", "build", "docs",
             "package", "migrate", "deploy", "notify"]) + "\n"}),
    "meeting-decisions: decisions written as a bullet list": ("meeting-decisions", {
        "summaries__beta_dot_md": "".join(f"- {d}\n" for d in ac.MEETINGS["beta.md"])}),
    "changelog: an extra blank line": ("changelog", {
        "CHANGELOG_dot_md": ac.CHANGELOG_WANT.replace("\n## 1.3.2", "\n\n## 1.3.2")}),
    "handbook: a number given as text": ("handbook", {
        "answers_dot_json": json.dumps({k: str(v) for k, v in ac.HANDBOOK_ANSWERS.items()})}),
    "handbook: the office named the way its heading is": ("handbook", {
        "answers_dot_json": json.dumps({**ac.HANDBOOK_ANSWERS, "q4": "Austin office"})}),
    "make-tests-pass: a loop instead of divmod": ("make-tests-pass", {
        "calc__money_dot_py": "def split_bill(total_cents, people):\n"
                              "    if people < 1:\n        raise ValueError('people must be at least 1')\n"
                              "    shares = [total_cents // people] * people\n"
                              "    for i in range(total_cents - sum(shares)):\n        shares[i] += 1\n"
                              "    return shares\n"}),
}
for name, (case_id, changes) in fine.items():
    passed, why = graded(case_id, **changes)
    check(f"accepted - {name}", passed, why)
check("schedule: every valid plan is accepted",
      all(graded("schedule", schedule_dot_json=json.dumps(plan))[0] for plan in ac._plans),
      str(len(ac._plans)))

# the file the runner reads is the one this module writes
exported = (ROOT / "evals" / "tasks.agent.jsonl").read_text()
loaded = [json.loads(line) for line in exported.splitlines()]
check("tasks.agent.jsonl is up to date and complete",
      exported == ac.export() and len(loaded) == 19 and len({c["id"] for c in loaded}) == 19
      and all(set(c) == {"id", "task", "files", "check_py"} for c in loaded),
      "run: python evals/agent_cases.py")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
