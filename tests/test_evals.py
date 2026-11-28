"""Check the eval runner against the mock endpoint. Run: python tests/test_evals.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "tests"))

import mock_llm  # noqa: E402

server, port = mock_llm.start()
tmp = Path(tempfile.mkdtemp(prefix="harness-eval-"))
os.environ.update(
    LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
    AGENT_WORKSPACE=str(tmp / "eval-workspace"), AGENT_SKILLS=str(tmp / "skills"),
    AGENT_TRACE=str(tmp / "trace.jsonl"), AGENT_CHECKPOINTS=str(tmp / "checkpoints"), AGENT_MAX_STEPS="6")

import run_evals  # noqa: E402

tasks = tmp / "tasks.jsonl"
tasks.write_text("\n".join(json.dumps(c) for c in [
    {"id": "note", "task": "[scenario:basic] eval note", "check": "grep -q hello notes/a.txt"},
    {"id": "recover", "task": "[scenario:badjson] eval recover", "check": "grep -q fixed b.txt"},
    {"id": "answer", "task": "[scenario:unknown] eval answer", "check": "grep -q 'unknown tool'"},
    {"id": "never", "task": "[scenario:steps] eval never", "check": "test -f finished.txt"},
    {"id": "python-check", "task": "[scenario:basic] eval with a check in Python",
     "check_py": "import pathlib, sys\nif pathlib.Path('notes/a.txt').read_text() != 'hello':\n"
                 "    sys.exit('wrong text')\nif sys.stdin.read() != 'DONE: hello':\n"
                 "    sys.exit('wrong answer')"},
    {"id": "python-check-fails", "task": "[scenario:basic] eval with a failing check",
     "check_py": "import sys\nsys.exit('the file is not what the task asked for')"},
]))
report = run_evals.main(str(tasks))
rows = {r["id"]: r for r in report["rows"]}
ok = (report["runs"] == 6 and report["pass_rate"] == 0.667
      and rows["note"]["passed"] and rows["note"]["steps"] == 3 and rows["note"]["tool_calls"] == 2
      and rows["recover"]["tool_failures"] == 1 and rows["answer"]["passed"]
      and not rows["never"]["passed"] and rows["never"]["hit_step_limit"]
      and report["step_limit_rate"] == 0.167 and not mock_llm.ERRORS)
print("PASS eval runner" if ok else f"FAIL eval runner  [{report}]")
checks = (rows["python-check"]["passed"] and rows["python-check"]["why"] == ""
          and not rows["python-check-fails"]["passed"]
          and rows["python-check-fails"]["why"] == "the file is not what the task asked for"
          and all(r["seconds"] >= 0 and r["reasoning_chars"] == 0 for r in report["rows"]))
print("PASS a check can be Python, and a failed check says why" if checks
      else f"FAIL a check can be Python, and a failed check says why  [{rows}]")

# the same task set at three effort levels: what each level buys, and what it costs
import subprocess  # noqa: E402

graded = tmp / "graded.jsonl"
graded.write_text("\n".join(json.dumps(c) for c in [
    {"id": "needs-think", "task": "[scenario:think] eval", "check": "grep -q noted"},
    {"id": "needs-check", "task": "[scenario:verify] eval", "check": "grep -q checked"},
]))
run = subprocess.run(
    [sys.executable, str(ROOT / "harness" / "run_evals.py"), str(graded), "1",
     "--effort", "low", "medium", "high"], capture_output=True, text=True, timeout=120)
table = [line.split() for line in run.stdout.strip().splitlines()[-3:]]
levels = (run.returncode == 0 and [row[:5] for row in table] == [["low", "0.0", "2.0", "20", "0"],
                                                                 ["medium", "0.5", "2.0", "20", "0"],
                                                                 ["high", "1.0", "3.5", "35", "0"]]
          and all(len(row) == 6 and float(row[5]) >= 0 for row in table) and not mock_llm.ERRORS)
print("PASS eval runner compares effort levels" if levels
      else f"FAIL eval runner compares effort levels  [{table} {run.stderr[-300:]}]")
from unittest.mock import patch  # noqa: E402

artifact_case = {"id": "failed-artifact", "task": "artifact-only failure check",
                 "files": {"finished.txt": "done"},
                 "check_py": "from pathlib import Path\nassert Path('finished.txt').is_file()"}
with patch.object(run_evals.h, "run_agent", side_effect=RuntimeError("model unavailable")):
    failed = run_evals.run_case(artifact_case)
failed_artifact = not failed["passed"] and failed["why"].startswith("RUN FAILED: RuntimeError")
print("PASS failed runs cannot pass an artifact-only check" if failed_artifact
      else f"FAIL failed runs cannot pass an artifact-only check  [{failed}]")
with patch.object(run_evals.h, "run_agent",
                  return_value="Stopped at the independent-review limit without a PASS verdict."):
    stopped = run_evals.run_case(artifact_case)
stopped_artifact = not stopped["passed"] and stopped["why"].startswith("Stopped at")
print("PASS stopped runs cannot pass an artifact-only check" if stopped_artifact
      else f"FAIL stopped runs cannot pass an artifact-only check  [{stopped}]")

# --delivery: the agent may run the operator's checks, and a case can be graded on that
delivery_dir = tmp / "eval-delivery"
delivery_dir.mkdir()
config = delivery_dir / "config.json"
config.write_text(json.dumps({"home": str(delivery_dir / "home"), "checks": {"tests": {
    "argv": [sys.executable, "-c", "import pathlib, sys\nsys.exit(0 if pathlib.Path('ok.txt').is_file() else 'ok.txt is missing')"],
    "timeout": 30}}}))
delivery_tasks = tmp / "delivery.jsonl"
delivery_tasks.write_text(json.dumps({
    "id": "with-checks", "task": "[scenario:delivery_eval] fix the workspace until the check passes",
    "check_py": "import pathlib, sys\nif not pathlib.Path('ok.txt').is_file():\n    sys.exit('no ok.txt')\n"
                "if not sys.stdin.read().startswith('DONE: exit=0'):\n    sys.exit('the agent never saw the check pass')"}) + "\n")
with_tools = subprocess.run(
    [sys.executable, str(ROOT / "harness" / "run_evals.py"), str(delivery_tasks), "--delivery", str(config)],
    capture_output=True, text=True, timeout=120)
try:
    delivery_report = json.loads(with_tools.stdout)
    row = delivery_report["rows"][0]
    delivery_ok = (with_tools.returncode == 0 and delivery_report["pass_rate"] == 1.0 and row["passed"]
                   and row["tool_calls"] == 3 and row["tool_failures"] == 0 and not mock_llm.ERRORS)
except (ValueError, KeyError, IndexError):
    delivery_ok = False
without_tools = subprocess.run(
    [sys.executable, str(ROOT / "harness" / "run_evals.py"), str(delivery_tasks)],
    capture_output=True, text=True, timeout=120)
try:
    plain_row = json.loads(without_tools.stdout)["rows"][0]
    delivery_ok = delivery_ok and not plain_row["passed"] and plain_row["tool_failures"] >= 1
except (ValueError, KeyError, IndexError):
    delivery_ok = False
print("PASS --delivery gives the agent the configured checks, and without it the case fails" if delivery_ok
      else f"FAIL --delivery gives the agent the configured checks  [{with_tools.stdout[-400:]} {with_tools.stderr[-300:]} "
           f"{without_tools.stdout[-300:]} {without_tools.stderr[-200:]}]")

# the shipped eval config works with this interpreter, and evals never get the git tools
import delivery_tools as dt  # noqa: E402

shipped = dt.load_config(str(ROOT / "evals" / "delivery.evals.json"))
run_evals.prepare_checks(shipped)
tests_check = shipped.checks["tests"]
run_evals.h.WORKSPACE.mkdir(parents=True, exist_ok=True)
(run_evals.h.WORKSPACE / "test_shipped.py").write_text(
    "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_one(self):\n        self.assertEqual(1, 1)\n")
code, output, _ = dt.run_check(shipped, tests_check)
shipped_ok = (tests_check.argv[0] == sys.executable and "-I" in tests_check.argv and code == 0
              and shipped.home == (ROOT / "evals" / "eval-home").resolve()
              and run_evals.eval_tools(["run_checks", "git_commit", "git_push_pr"]) == run_evals.h.ORCHESTRATOR_TOOLS + ["run_checks"])
try:
    run_evals.prepare_checks(type(shipped)(shipped.source, shipped.home, {"odd": type(tests_check)(
        "odd", ("no-such-program-xyz", "--version"), 10.0, ())}, (), {}, None, "docs/adr", ()))
    missing_program = False
except SystemExit as err:
    missing_program = "no-such-program-xyz" in str(err)
print("PASS the shipped eval config runs here and evals offer run_checks only" if shipped_ok and missing_program
      else f"FAIL the shipped eval config runs here and evals offer run_checks only  [{tests_check} {code} {output[-200:]} {missing_program}]")
server.shutdown()
sys.exit(0 if ok and checks and levels and failed_artifact and stopped_artifact and delivery_ok
         and shipped_ok and missing_program else 1)
