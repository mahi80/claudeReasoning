"""run_evals.py - replay a fixed task set and score it from the workspace and the trace.

Usage: AGENT_WORKSPACE=/tmp/eval-workspace python run_evals.py tasks.jsonl [repeats]
           [--effort low medium high ...] [--shard 0/3] [--delivery CONFIG]
Each line of tasks.jsonl is a JSON object with the keys:
  id, task, files (optional: {path: text}), and check (a shell command) or check_py
  (Python source)
The check runs in the workspace with the agent's final answer on stdin; exit 0 = pass.
evals/tasks.example.jsonl is a three-case sample; evals/tasks.agent.jsonl is the real set.
Name several effort levels to see what each one buys: pass rate against tokens spent.
--delivery loads an operator config (harness/delivery_tools.py; evals/delivery.evals.json
is a ready-made one) and gives the agent its checks through run_checks, and nothing else:
git tools in the config are not offered, since a case workspace is wiped per case. A check
whose program is "python" runs with this interpreter; any other program must be on PATH.
The config and its home folder must lie outside the eval workspace, and each check's argv
must make sense in a fresh case workspace.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from openai import APITimeoutError

import mini_harness as h


def run_case(case: dict, effort: str = "medium", tools: list[str] | None = None,
             assisted: bool = False) -> dict:
    assert "eval" in h.WORKSPACE.name, "point AGENT_WORKSPACE at a dedicated eval folder"
    offset = h.TRACE_FILE.stat().st_size if h.TRACE_FILE.exists() else 0
    started = time.time()
    outcome, passed = "fail", False
    try:
        shutil.rmtree(h.WORKSPACE, ignore_errors=True)
        h.WORKSPACE.mkdir(parents=True)
        for path, text in case.get("files", {}).items():
            h.write_file(path, text)
        granted = h.ORCHESTRATOR_TOOLS if tools is None else tools
        answer = h.run_agent(case["task"], h.orchestrator_system(), granted, effort=effort)
    except (TimeoutError, APITimeoutError) as err:
        outcome, answer = "timeout", f"RUN FAILED: {type(err).__name__}"
    except Exception as err:
        outcome, answer = "invalid", f"RUN FAILED: {type(err).__name__}"
    seconds = round(time.time() - started, 1)
    events, why = [], answer[:200]
    if h.TRACE_FILE.exists():
        try:
            with h.TRACE_FILE.open(encoding="utf-8") as stream:
                stream.seek(offset)
                events = [json.loads(line) for line in stream]
            for event in events:
                if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                    raise ValueError("invalid trace event")
                if event["event"] == "model" and (
                        not isinstance(event.get("agent"), str) or any(
                            type(event.get(key)) is not int or event[key] < 0
                            for key in ("output_tokens", "reasoning_chars"))):
                    raise ValueError("invalid model metrics")
                if event["event"] == "tool" and type(event.get("failed")) is not bool:
                    raise ValueError("invalid tool metrics")
                if event["event"] == "budget_limit" and any(
                        not isinstance(event.get(key), str) for key in ("agent", "reason")):
                    raise ValueError("invalid budget event")
        except (OSError, ValueError):
            events, outcome, why = [], "invalid", "RUN FAILED: invalid runtime trace"
    if outcome == "fail":
        if any(e["event"] == "budget_limit" and e.get("agent") == "main"
               and e.get("reason") == "time budget" for e in events):
            outcome = "timeout"
        elif not answer.startswith(("RUN FAILED:", "Stopped at")):
            try:
                if "check_py" in case:
                    compile(case["check_py"], "<eval grader>", "exec")
                    command = [sys.executable, "-I", "-c", case["check_py"]]
                else:
                    command = case["check"]
                check = subprocess.run(command, shell="check_py" not in case, cwd=h.WORKSPACE,
                                       input=answer, text=True, capture_output=True, timeout=120)
                passed = check.returncode == 0
                outcome = "pass" if passed else "invalid" if check.returncode < 0 else "fail"
                why = (check.stderr or check.stdout)[-200:].strip()
                if check.returncode < 0:
                    why = f"CHECK FAILED: grader terminated ({check.returncode})"
            except subprocess.TimeoutExpired:
                outcome, why = "timeout", "the check timed out"
            except Exception as err:
                outcome, why = "invalid", f"CHECK FAILED: {type(err).__name__}"
    if passed and assisted:
        outcome = "assisted"
    tools = [e for e in events if e["event"] == "tool"]
    calls = [e for e in events if e["event"] == "model"]
    return {"id": case["id"], "passed": passed, "outcome": outcome, "assisted": assisted,
            "steps": sum(e["agent"] == "main" for e in calls),
            "output_tokens": sum(e["output_tokens"] for e in calls),
            "reasoning_chars": sum(e["reasoning_chars"] for e in calls),
            "seconds": seconds,
            "tool_calls": len(tools), "tool_failures": sum(e["failed"] for e in tools),
            "hit_step_limit": any(e["event"] == "step_limit" for e in events),
            "why": "" if passed else why}


def eval_tools(registered: list[str]) -> list[str]:
    """Evals get the checks only: a case workspace is wiped per case and must never be committed."""
    return h.ORCHESTRATOR_TOOLS + [name for name in registered if name == "run_checks"]


def prepare_checks(config) -> None:
    """Make the config's checks runnable here: this interpreter for 'python', every program present."""
    for name, check in list(config.checks.items()):
        argv = list(check.argv)
        if argv[0] in ("python", "python3"):
            argv[0] = sys.executable
            config.checks[name] = type(check)(check.name, tuple(argv), check.timeout, check.env)
        elif shutil.which(argv[0]) is None:
            raise SystemExit(f"check {name}: {argv[0]} is not on PATH, so the agent could never run it")


def main(path: str, repeats: int = 1, effort: str = "medium", shard: str = "0/1",
         tools: list[str] | None = None, assisted: bool = False) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    part, parts = map(int, shard.split("/"))
    if not 0 <= part < parts:
        raise ValueError("shard must be I/N with 0 <= I < N")
    lines = Path(path).read_text().splitlines()
    cases = [json.loads(line) for line in lines if line.strip()][part::parts]
    rows = [run_case(c, effort, tools, assisted=assisted) for c in cases for _ in range(repeats)]
    outcomes = {name: sum(r["outcome"] == name for r in rows)
                for name in ("pass", "fail", "invalid", "timeout", "assisted")}
    runs, denominator = len(rows), len(rows) or 1
    calls = sum(r["tool_calls"] for r in rows) or 1
    report = {"effort": effort, "runs": runs, "outcomes": outcomes,
              "assisted_runs": sum(r["assisted"] for r in rows),
              "pass_rate": round(outcomes["pass"] / runs, 3) if runs else None,
              "avg_steps": round(sum(r["steps"] for r in rows) / denominator, 1),
              "avg_output_tokens": round(
                  sum(r["output_tokens"] for r in rows) / denominator),
              "avg_reasoning_chars": round(
                  sum(r["reasoning_chars"] for r in rows) / denominator),
              "avg_seconds": round(sum(r["seconds"] for r in rows) / denominator, 1),
              "tool_failure_rate": round(
                  sum(r["tool_failures"] for r in rows) / calls, 3),
              "step_limit_rate": round(
                  sum(r["hit_step_limit"] for r in rows) / denominator, 3),
              "rows": rows}
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Replay a task set and score it.")
    cli.add_argument("tasks", help="JSON Lines file, one task per line")
    cli.add_argument("repeats", nargs="?", type=int, default=1)
    cli.add_argument("--effort", nargs="+", choices=h.LADDER, default=["medium"])
    cli.add_argument("--shard", default="0/1", metavar="I/N",
                     help="run every Nth case starting at case I, to split a set over processes")
    cli.add_argument("--delivery", default="", metavar="CONFIG",
                     help="delivery config whose checks the agent may run through run_checks")
    cli.add_argument("--assisted", action="store_true",
                     help="mark these runs as operator-assisted; successful runs do not count as unassisted passes")
    args = cli.parse_args()
    tools = None
    if args.delivery:
        import delivery_tools
        registered = delivery_tools.register(args.delivery)
        prepare_checks(delivery_tools.CONFIG)
        tools = eval_tools(registered)
        dropped = sorted(set(registered) - set(tools))
        if dropped:
            print(f"evals offer run_checks only; not given to the agent: {', '.join(dropped)}", file=sys.stderr)
    try:
        reports = [main(args.tasks, args.repeats, level, args.shard, tools, assisted=args.assisted)
                   for level in args.effort]
    finally:
        if args.delivery:
            delivery_tools.close()
    if len(reports) > 1:                      # the trade-off, one line per level
        print(f"{'effort':8}{'pass rate':>10}{'avg steps':>11}{'avg output tokens':>19}"
              f"{'avg reasoning chars':>21}{'avg seconds':>13}")
        for r in reports:
            rate = r["pass_rate"] if r["pass_rate"] is not None else "n/a"
            print(f"{r['effort']:8}{rate:>10}{r['avg_steps']:>11}"
                  f"{r['avg_output_tokens']:>19}{r['avg_reasoning_chars']:>21}"
                  f"{r['avg_seconds']:>13}")
