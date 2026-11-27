"""run_evals.py - replay a fixed task set and score it from the workspace and the trace.

Usage: AGENT_WORKSPACE=/tmp/eval-workspace python run_evals.py tasks.jsonl [repeats]
           [--effort low medium high ...]
Each line of tasks.jsonl is a JSON object with the keys:
  id, task, files (optional: {path: text}), and check (a shell command) or check_py
  (Python source)
The check runs in the workspace with the agent's final answer on stdin; exit 0 = pass.
evals/tasks.example.jsonl is a three-case sample; evals/tasks.agent.jsonl is the real set.
Name several effort levels to see what each one buys: pass rate against tokens spent.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import mini_harness as h


def run_case(case: dict, effort: str = "medium") -> dict:
    assert "eval" in h.WORKSPACE.name, "point AGENT_WORKSPACE at a dedicated eval folder"
    shutil.rmtree(h.WORKSPACE, ignore_errors=True)        # every case starts clean
    h.WORKSPACE.mkdir(parents=True)
    for path, text in case.get("files", {}).items():
        h.write_file(path, text)
    offset = h.TRACE_FILE.stat().st_size if h.TRACE_FILE.exists() else 0
    started = time.time()
    try:
        answer = h.run_agent(case["task"], h.orchestrator_system(), h.ORCHESTRATOR_TOOLS,
                             effort=effort)
    except Exception as err:                  # one server error must not end the whole set
        answer = f"RUN FAILED: {type(err).__name__}: {err}"
    seconds = round(time.time() - started, 1)
    command = [sys.executable, "-c", case["check_py"]] if "check_py" in case else case["check"]
    try:
        check = subprocess.run(command, shell="check_py" not in case, cwd=h.WORKSPACE,
                               input=answer, text=True, capture_output=True, timeout=120)
        passed, why = check.returncode == 0, (check.stderr or check.stdout)[-200:].strip()
    except subprocess.TimeoutExpired:
        passed, why = False, "the check timed out"
    if answer.startswith("RUN FAILED"):
        why = answer[:200]
    with h.TRACE_FILE.open() as f:
        f.seek(offset)
        events = [json.loads(line) for line in f]
    tools = [e for e in events if e["event"] == "tool"]
    calls = [e for e in events if e["event"] == "model"]       # every agent in the run
    return {"id": case["id"], "passed": passed,
            "steps": sum(e["agent"] == "main" for e in calls),
            "output_tokens": sum(e["output_tokens"] for e in calls),
            "reasoning_chars": sum(e["reasoning_chars"] for e in calls),
            "seconds": seconds,
            "tool_calls": len(tools), "tool_failures": sum(e["failed"] for e in tools),
            "hit_step_limit": any(e["event"] == "step_limit" for e in events),
            "why": "" if passed else why}


def main(path: str, repeats: int = 1, effort: str = "medium") -> dict:
    lines = Path(path).read_text().splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    rows = [run_case(c, effort) for c in cases for _ in range(repeats)]
    calls = sum(r["tool_calls"] for r in rows) or 1
    report = {"effort": effort, "runs": len(rows),
              "pass_rate": round(sum(r["passed"] for r in rows) / len(rows), 3),
              "avg_steps": round(sum(r["steps"] for r in rows) / len(rows), 1),
              "avg_output_tokens": round(
                  sum(r["output_tokens"] for r in rows) / len(rows)),
              "avg_reasoning_chars": round(
                  sum(r["reasoning_chars"] for r in rows) / len(rows)),
              "avg_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 1),
              "tool_failure_rate": round(
                  sum(r["tool_failures"] for r in rows) / calls, 3),
              "step_limit_rate": round(
                  sum(r["hit_step_limit"] for r in rows) / len(rows), 3),
              "rows": rows}
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Replay a task set and score it.")
    cli.add_argument("tasks", help="JSON Lines file, one task per line")
    cli.add_argument("repeats", nargs="?", type=int, default=1)
    cli.add_argument("--effort", nargs="+", choices=h.LADDER, default=["medium"])
    args = cli.parse_args()
    reports = [main(args.tasks, args.repeats, level) for level in args.effort]
    if len(reports) > 1:                      # the trade-off, one line per level
        print(f"{'effort':8}{'pass rate':>10}{'avg steps':>11}{'avg output tokens':>19}"
              f"{'avg reasoning chars':>21}{'avg seconds':>13}")
        for r in reports:
            print(f"{r['effort']:8}{r['pass_rate']:>10}{r['avg_steps']:>11}"
                  f"{r['avg_output_tokens']:>19}{r['avg_reasoning_chars']:>21}"
                  f"{r['avg_seconds']:>13}")
