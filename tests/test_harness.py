"""End-to-end tests of mini_harness against the mock endpoint. Run: python tests/test_harness.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "tests"))

import mock_llm  # noqa: E402

server, port = mock_llm.start()
tmp = Path(tempfile.mkdtemp(prefix="harness-test-"))
os.environ.update(
    LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
    AGENT_WORKSPACE=str(tmp / "workspace"), AGENT_SKILLS=str(tmp / "skills"),
    AGENT_TRACE=str(tmp / "trace.jsonl"), AGENT_CHECKPOINTS=str(tmp / "checkpoints"),
    AGENT_MAX_STEPS="15", AGENT_CONTEXT_BUDGET="3000")

import mini_harness as h  # noqa: E402

h.WORKSPACE.mkdir(parents=True)
(h.SKILLS_DIR / "report-style").mkdir(parents=True)
(h.SKILLS_DIR / "report-style" / "SKILL.md").write_text(
    "---\nname: report-style\ndescription: House style for written reports; load before "
    "drafting any report.\n---\n\nUse short sentences. End with a list of open items.\n")

SYSTEM = h.orchestrator_system()
ALL = h.ORCHESTRATOR_TOOLS
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def events(kind: str) -> list[dict]:
    return [e for e in map(json.loads, h.TRACE_FILE.read_text().splitlines())
            if e["event"] == kind]


# 1. basic loop: write, read, answer
out = h.run_agent("[scenario:basic] make a note", SYSTEM, ALL)
check("basic tool loop", out == "DONE: hello" and (h.WORKSPACE / "notes/a.txt").read_text() == "hello", out)

# 2. skills index is in the system prompt, one line, without the body
check("skills index in system prompt",
      "- report-style: House style for written reports" in SYSTEM and "short sentences" not in SYSTEM)

# 3. malformed JSON arguments are fed back and the model recovers
out = h.run_agent("[scenario:badjson] write b", SYSTEM, ALL)
check("bad JSON fed back, then recovery", out == "recovered" and (h.WORKSPACE / "b.txt").read_text() == "fixed", out)

# 4. unknown tool name is reported with the list of real tools
out = h.run_agent("[scenario:unknown] x", SYSTEM, ALL)
check("unknown tool reported", out.startswith("saw: ERROR: unknown tool 'delete_everything'") and "read_file" in out, out)

# 5. identical repeated call is stopped on the third attempt
out = h.run_agent("[scenario:loop] x", SYSTEM, ALL)
check("repeat-call loop broken", out == "gave up", out)

# 6. two subagents in one turn run in parallel, each with its own context
t0 = time.time()
out = h.run_agent("[scenario:parallel] split the work", SYSTEM, ALL)
elapsed = time.time() - t0
both = "report: p1.txt written" in out and "report: p2.txt written" in out
files = (h.WORKSPACE / "p1.txt").exists() and (h.WORKSPACE / "p2.txt").exists()
check("parallel subagents", both and files and elapsed < 1.45, f"{elapsed:.2f}s {out}")
sub_requests = [r for r in mock_llm.REQUESTS if "[scenario:sub]" in json.dumps(r["messages"][:2])]
check("subagent context is fresh (no orchestrator history)",
      all("split the work" not in json.dumps(r["messages"]) for r in sub_requests) and len(sub_requests) == 4)
check("subagents cannot spawn subagents or rewrite the plan",
      all(not {"spawn_agent", "update_plan"} & {t["function"]["name"] for t in r["tools"]}
          for r in sub_requests))

# 7. compaction keeps the conversation valid and the run finishes
out = h.run_agent("[scenario:compact] long job", SYSTEM, ALL)
compact_runs = [r for r in mock_llm.REQUESTS
                if len(r["messages"]) > 1 and "[scenario:compact]" in r["messages"][1]["content"]]
compacted = [r for r in compact_runs
             if "[Summary of your earlier work]" in r["messages"][1]["content"]]
check("compaction triggered and run finished",
      out == "finished compact" and len(events("compact")) >= 1 and len(compacted) >= 1,
      f"{out} compact_events={len(events('compact'))}")
biggest = max(len(json.dumps(r["messages"])) // 4 for r in compact_runs)
check("prompt stays bounded after compaction", biggest < 3000 + 4 * 1200, str(biggest))

# 8. step limit stops a run that never finishes
out = h.run_agent("[scenario:steps] never ends", SYSTEM, ALL)
check("step limit enforced", out.startswith("Stopped at the 15-step limit") and len(events("step_limit")) == 1, out)
check("checkpoint written", len(list(h.CHECKPOINT_DIR.glob("*.json"))) >= 1)

# 9. approvals: destructive and chained commands denied, read-only allowed
out = h.run_agent("[scenario:denied] shell", SYSTEM, ALL)
parts = out.split(" || ")
check("shell approvals", len(parts) == 3 and parts[0].startswith("DENIED") and parts[1].startswith("DENIED")
      and parts[2].startswith("exit=0"), out)

cases = {"ls -la": True, "grep -n TODO notes/a.txt": True, "ls && rm x": False, "cat a > b": False,
         "cat /etc/passwd": False, "cat ../secret": False, "find . -delete": False, "rm x": False,
         "ls $(rm x)": False, "": False, "cat 'unterminated": False}
wrong = {c: h.is_read_only(c) for c, want in cases.items() if h.is_read_only(c) != want}
check("read-only allow-list classification", not wrong, str(wrong))

# 10. path jail
out = h.run_agent("[scenario:jail] escape", SYSTEM, ALL)
check("workspace jail", "PermissionError" in out and "outside the workspace" in out, out)

# 11. skill body loads on demand
out = h.run_agent("[scenario:skill] report", SYSTEM, ALL)
check("skill loaded on demand", "End with a list of open items." in out, out)

# 12. non-parallel tools in one turn run in order
out = h.run_agent("[scenario:sequence] two edits", SYSTEM, ALL)
check("ordered execution of dependent calls", out == "q=second", out)

# long tasks: the saved plan is pinned into every prompt and can be updated
out = h.run_agent("[scenario:plan] long job with a plan", SYSTEM, ALL)
check("plan pinned into each turn", out == "plan seen"
      and (h.WORKSPACE / "plan-seen.txt").read_text() == "True", out)
h.run_agent("[scenario:basic] task after a planned one", SYSTEM, ALL)
later = [r for r in mock_llm.REQUESTS if len(r["messages"]) > 1
         and "task after a planned one" in r["messages"][1]["content"]]
check("a new task does not inherit an old plan",
      later and all("[Current plan]" not in r["messages"][1]["content"] for r in later))

# long tasks: a run cut off at the step limit resumes from its checkpoint
task = "[scenario:long] write twenty files"
first = h.run_agent(task, SYSTEM, ALL)
before = len(mock_llm.REQUESTS)
second = h.run_agent(task, SYSTEM, ALL, resume=True)
resumed = mock_llm.REQUESTS[before:]
check("resume continues from the checkpoint",
      first.startswith("Stopped at the 15-step limit") and second == "all 20 written"
      and len(resumed) == 6 and len(resumed[0]["messages"]) == 2 + 15 * 2
      and (h.WORKSPACE / "l19.txt").exists(), f"{first} / {second} / {len(resumed)}")
check("resume event traced", len(events("resume")) == 1)

# 13. MCP tools via the bridge
from mcp import StdioServerParameters  # noqa: E402
import mcp_bridge  # noqa: E402

names = mcp_bridge.connect("demo", StdioServerParameters(
    command=sys.executable, args=[str(ROOT / "tests" / "demo_mcp_server.py")]))
out = h.run_agent("[scenario:mcp] add", SYSTEM, ALL + names)
check("MCP tool through bridge", names == ["demo__add"] and out == "sum=5", f"{names} {out}")
mcp_bridge.close()

# every harness request streamed (needed behind proxies with idle limits)
check("harness always streams", all(r.get("stream") is True for r in mock_llm.REQUESTS))

# smoke test script works against the endpoint (non-streaming, strict tool schema)
import subprocess  # noqa: E402

smoke = subprocess.run([sys.executable, str(ROOT / "harness" / "smoke_test.py")],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "SMOKE_PROMPT": "[scenario:basic] smoke"})
check("smoke_test.py", smoke.returncode == 0 and smoke.stdout.startswith("OK write_file"),
      smoke.stdout + smoke.stderr)

# 14. the mock (acting as a strict chat template) rejected nothing
check("no malformed requests sent", not mock_llm.ERRORS, "; ".join(mock_llm.ERRORS))

# 15. trace has model and tool events with the fields the evals rely on
m, t = events("model"), events("tool")
check("trace written", len(m) > 30 and len(t) > 30 and {"agent", "step", "prompt_tokens"} <= set(m[0])
      and {"tool", "chars", "failed"} <= set(t[0]), f"{len(m)} {len(t)}")

# 16. wrong API key is refused by the server
bad = h.OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key="wrong")
try:
    bad.chat.completions.create(model="mock", messages=[{"role": "user", "content": "hi"}], stream=True)
    check("API key enforced", False, "request was accepted")
except Exception as err:
    check("API key enforced", "401" in str(err) or "bad api key" in str(err), str(err))

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
server.shutdown()
sys.exit(1 if failed else 0)
