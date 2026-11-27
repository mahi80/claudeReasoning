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
server.shutdown()
sys.exit(0 if ok else 1)
