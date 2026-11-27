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
]))
report = run_evals.main(str(tasks))
rows = {r["id"]: r for r in report["rows"]}
ok = (report["runs"] == 4 and report["pass_rate"] == 0.75
      and rows["note"]["passed"] and rows["note"]["steps"] == 3 and rows["note"]["tool_calls"] == 2
      and rows["recover"]["tool_failures"] == 1 and rows["answer"]["passed"]
      and not rows["never"]["passed"] and rows["never"]["hit_step_limit"]
      and report["step_limit_rate"] == 0.25 and not mock_llm.ERRORS)
print("PASS eval runner" if ok else "FAIL eval runner")

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
levels = (run.returncode == 0 and table == [["low", "0.0", "2.0", "20"],
                                             ["medium", "0.5", "2.0", "20"],
                                             ["high", "1.0", "3.5", "35"]]
          and not mock_llm.ERRORS)
print("PASS eval runner compares effort levels" if levels
      else f"FAIL eval runner compares effort levels  [{table} {run.stderr[-300:]}]")
server.shutdown()
sys.exit(0 if ok and levels else 1)
