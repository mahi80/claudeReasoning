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
    AGENT_MAX_STEPS="15", AGENT_CONTEXT_BUDGET="3000",
    # thinking is switched the way Mistral Small 4 does it; a fragment may carry any field
    LLM_THINKING=json.dumps({
        "off": {"reasoning_effort": "none"},
        "on": {"reasoning_effort": "high", "temperature": 0.7},
        "max": {"reasoning_effort": "high", "chat_template_kwargs": {"depth": "max"}}}),
    LLM_EXTRA_BODY=json.dumps({"chat_template_kwargs": {"custom": 1}}))

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

# with nobody to approve, the model is told so up front, and told what to use instead
sent = [r for r in mock_llm.REQUESTS if "[scenario:denied] shell" in json.dumps(r["messages"][:2])]
check("unattended run: said in the system prompt and in the refusal",
      h.unattended() and h.UNATTENDED in sent[0]["messages"][0]["content"]
      and parts[0].startswith("DENIED: nobody is available to approve run_shell in this run")
      and "write_file" in parts[0], parts[0])
h.ask_operator = lambda name, args: False              # an operator who says no
out = h.run_agent("[scenario:denied] with an operator", SYSTEM, ALL)
sent = [r for r in mock_llm.REQUESTS if "with an operator" in json.dumps(r["messages"][:2])]
h.ask_operator = h.no_operator
check("attended run: no such notice, and the refusal is the operator's",
      "Nobody is available" not in sent[0]["messages"][0]["content"] and out.split(" || ")[0]
      == "DENIED: the operator did not approve this action. Continue without it.", out)

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

# ---------------------------------------------------------------- effort levels
def run_at(effort: str, task: str) -> tuple[str, list[dict], list[dict]]:
    """Run one task at one level; return the answer, its requests and its trace events."""
    r0, t0 = len(mock_llm.REQUESTS), len(h.TRACE_FILE.read_text().splitlines())
    answer = h.run_agent(task, SYSTEM, ALL, effort=effort)
    lines = h.TRACE_FILE.read_text().splitlines()[t0:]
    return answer, mock_llm.REQUESTS[r0:], [json.loads(line) for line in lines]


def thinking(requests: list[dict]) -> list[bool]:
    return [r.get("reasoning_effort") == "high" for r in requests]


def offered(request: dict) -> set[str]:
    return {t["function"]["name"] for t in request.get("tools", [])}


def kinds(trace_events: list[dict], kind: str) -> list[dict]:
    return [e for e in trace_events if e["event"] == kind]


# low: no thinking, no think tool, no delegation, the level's line in the system prompt
out, reqs, evs = run_at("low", "[scenario:basic] low effort")
check("low: thinking off on every call", out == "DONE: hello" and thinking(reqs) == [False] * 3,
      f"{out} {thinking(reqs)}")
check("low: think and spawn_agent are not offered",
      not {"think", "spawn_agent"} & offered(reqs[0]) and "update_plan" in offered(reqs[0]))
check("effort guidance is appended to the system prompt",
      reqs[0]["messages"][0]["content"].endswith(h.GUIDANCE["low"])
      and reqs[0]["messages"][0]["content"].startswith(SYSTEM))

# medium: thinking on the first step and on the step after a failed tool call
out, reqs, evs = run_at("medium", "[scenario:basic] medium effort")
check("medium: thinking on the first step only", thinking(reqs) == [True, False, False],
      str(thinking(reqs)))
check("reasoning is read from its own field and traced",
      [e["reasoning_chars"] > 0 for e in kinds(evs, "model")] == [True, False, False]
      and all(e["output_tokens"] == 10 for e in kinds(evs, "model")))
check("the trace records which thinking each call asked for",
      [e["thinking"] for e in kinds(evs, "model")] == ["on", "off", "off"])
out, reqs, evs = run_at("medium", "[scenario:badjson] think after the error")
check("medium: thinking returns after a failed tool call",
      out == "recovered" and thinking(reqs) == [True, True, False], str(thinking(reqs)))
check("a thinking fragment can carry other request fields",
      [r["temperature"] for r in reqs] == [0.7, 0.7, 0.2], str([r["temperature"] for r in reqs]))

# a model that cannot switch thinking mid-task gets one choice per task instead
h.THINKING_SCOPE = "task"
out, reqs, evs = run_at("medium", "[scenario:basic] medium, one choice per task")
check("task scope: medium thinks on every step",
      thinking(reqs) == [True] * 3 and [e["thinking"] for e in kinds(evs, "model")] == ["on"] * 3,
      str(thinking(reqs)))
h.THINKING["brief"] = {"reasoning_effort": "high", "thinking_token_budget": 256}
out, reqs, evs = run_at("medium", "[scenario:basic] medium, thinking with a budget")
check("task scope: medium uses the brief fragment when one is defined",
      [r.get("thinking_token_budget") for r in reqs] == [256] * 3
      and [e["thinking"] for e in kinds(evs, "model")] == ["brief"] * 3,
      str([r.get("thinking_token_budget") for r in reqs]))
out, reqs, evs = run_at("low", "[scenario:basic] low, task scope")
_, high, _ = run_at("high", "[scenario:verify] high, task scope")
check("task scope: low stays off and high stays fully on",
      thinking(reqs) == [False] * 3 and all(thinking(high))
      and all("thinking_token_budget" not in r for r in reqs + high))
del h.THINKING["brief"]
h.THINKING_SCOPE = "step"

# high: thinking on every call, a larger reply budget, and one self-check
out, reqs, evs = run_at("high", "[scenario:verify] check before answering")
check("high: self-check runs before the answer is accepted",
      out == "checked answer: v1" and len(reqs) == 4 and all(thinking(reqs)), f"{out} {len(reqs)}")
out, reqs, evs = run_at("high", "[scenario:verify] confirm it")
check("high: a confirmed self-check returns the first answer in full",
      out == "first answer" and len(reqs) == 3, out)
out, reqs, evs = run_at("medium", "[scenario:verify] no check at medium")
check("medium: no self-check", out == "first answer" and len(reqs) == 2, out)
sizes = {}
for level in h.LADDER:
    _, reqs, _ = run_at(level, f"[scenario:think] reply size at {level}")
    sizes[level] = reqs[0]["max_tokens"]
check("reply budget grows with the level",
      sizes == {"low": 4096, "medium": 4096, "high": 8192, "xhigh": 8192, "max": 16384},
      str(sizes))
check("max uses its own thinking fragment, merged with LLM_EXTRA_BODY",
      reqs[0]["chat_template_kwargs"] == {"custom": 1, "depth": "max"},
      str(reqs[0].get("chat_template_kwargs")))

# the think tool is a no-op the model can call between other tools
out, reqs, evs = run_at("medium", "[scenario:think] reason between calls")
check("think tool", out == "think said: noted" and "think" in offered(reqs[0]), out)

# xhigh: an independent reviewer with a fresh context can send the work back once
out, reqs, evs = run_at("xhigh", "[scenario:review] reviewed once")
reviewer = [r for r in reqs if r["messages"][0]["content"].startswith("You are an independent")]
check("xhigh: a failed review sends the work back",
      out == "answer two" and (h.WORKSPACE / "r.txt").read_text() == "right"
      and [e["passed"] for e in kinds(evs, "review")] == [False], out)
check("reviewer has a fresh context and read-only tools",
      len(reviewer) == 2 and len(reviewer[0]["messages"]) == 2
      and offered(reviewer[0]) == {"read_file", "list_dir", "think"}
      and "answer one" in reviewer[0]["messages"][1]["content"])
out, reqs, evs = run_at("max", "[scenario:review] reviewed twice")
check("max: second review passes after the fix",
      out == "answer two" and [e["passed"] for e in kinds(evs, "review")] == [False, True], out)
out, reqs, evs = run_at("high", "[scenario:review] no reviewer at high")
check("high: no reviewer", out == "answer one" and not kinds(evs, "review"), out)
out, reqs, evs = run_at("xhigh", "[scenario:review] stubborn agent")
check("an agent that only confirms after a rejection keeps its full answer",
      out == "answer one" and [e["passed"] for e in kinds(evs, "review")] == [False], out)
out, reqs, evs = run_at("xhigh", "[scenario:review] unclear verdict")
check("a verdict that is not FAIL is accepted",
      out == "answer one" and [e["passed"] for e in kinds(evs, "review")] == [True], out)

# worker budget: medium allows two workers, high allows four, low has no spawn tool
out, reqs, evs = run_at("medium", "[scenario:fanout] prefix=m")
made = sorted(f.name for f in h.WORKSPACE.glob("m?.txt"))
check("medium: third worker refused",
      out.count("ERROR: this effort level allows 2 worker agents") == 1
      and out.count("written") == 2 and len(made) == 2, f"{out} {made}")
out, reqs, evs = run_at("high", "[scenario:fanout] prefix=h")
check("high: three workers run", out.count("written") == 3 and "ERROR" not in out
      and len(list(h.WORKSPACE.glob("h?.txt"))) == 3, out)

# a reply that is all thinking and no answer is retried once with thinking off
out, reqs, evs = run_at("medium", "[scenario:blank] empty reply")
check("blank reply retried without thinking",
      out == "answer after retry" and thinking(reqs) == [True, False]
      and len(kinds(evs, "blank")) == 1, f"{out} {thinking(reqs)}")

# returned reasoning: off by default, on with LLM_KEEP_REASONING=1
h.KEEP_REASONING = True
out, reqs, evs = run_at("high", "[scenario:basic] keep the thoughts")
h.KEEP_REASONING = False
kept = [m.get("reasoning") for m in reqs[-1]["messages"] if m.get("tool_calls")]
check("reasoning is sent back between tool calls when enabled",
      kept == ["Weighing the next step. Decided."] * 2, str(kept))
out, reqs, evs = run_at("high", "[scenario:basic] drop the thoughts")
check("reasoning is not sent back by default",
      all("reasoning" not in m for r in reqs for m in r["messages"]))

# without AGENT_MAX_STEPS the level sets the step limit
h.MAX_STEPS = 0
out, reqs, evs = run_at("low", "[scenario:steps] preset limit")
h.MAX_STEPS = 15
check("step limit comes from the level", out.startswith("Stopped at the 8-step limit"), out)

# escalation: a stalled run resumes one level up; a rejected answer is retried one level up
r0, t0 = len(mock_llm.REQUESTS), len(h.TRACE_FILE.read_text().splitlines())
out = h.run_escalating("[scenario:long] escalate from low", SYSTEM, ALL, start="low")
evs = [json.loads(line) for line in h.TRACE_FILE.read_text().splitlines()[t0:]]
check("escalation resumes a stalled run one level up",
      out == "all 20 written" and [e["effort"] for e in kinds(evs, "run")] == ["low", "medium"]
      and len(kinds(evs, "escalate")) == 1 and len(kinds(evs, "resume")) == 1
      and len(mock_llm.REQUESTS) - r0 == 21, f"{out} {len(mock_llm.REQUESTS) - r0}")
t0 = len(h.TRACE_FILE.read_text().splitlines())
out = h.run_escalating("[scenario:think] escalate on a failed check", SYSTEM, ALL, start="low",
                       accept=lambda answer: answer == "think said: noted")
evs = [json.loads(line) for line in h.TRACE_FILE.read_text().splitlines()[t0:]]
check("escalation retries a rejected answer one level up",
      out == "think said: noted" and [e["effort"] for e in kinds(evs, "run")] == ["low", "medium"],
      out)

# the reply budget and the prompt budget share the server's context window
keep = (h.CONTEXT_WINDOW, h.CONTEXT_BUDGET)
h.CONTEXT_WINDOW, h.CONTEXT_BUDGET = 32768, 24000
small = {name: h.budgets(level) for name, level in h.EFFORTS.items()}
h.CONTEXT_WINDOW = 65536
large = h.budgets(h.EFFORTS["max"])
h.CONTEXT_WINDOW, h.CONTEXT_BUDGET = keep
check("budgets fit the context window",
      small == {"low": (4096, 24000), "medium": (4096, 24000), "high": (8192, 20480),
                "xhigh": (8192, 20480), "max": (16384, 12288)} and large == (16384, 24000),
      f"{small} {large}")


# compaction never leaves a follow-up user message or a tool result at the front
def pair(n: int, calls: int = 1) -> list[dict]:
    ids = [f"k{n}x{c}" for c in range(calls)]
    return [{"role": "assistant", "content": None, "tool_calls": [
        {"id": i, "type": "function", "function": {"name": "list_dir", "arguments": "{}"}}
        for i in ids]}] + [{"role": "tool", "tool_call_id": i, "content": "ok"} for i in ids]


history = (pair(0) + pair(1) + pair(2) + pair(3)
           + [{"role": "assistant", "content": "draft"},
              {"role": "user", "content": h.VERIFY_PROMPT}]
           + pair(4) + pair(5) + pair(6, calls=2))
recent, summary = h.compact(history, "")
try:
    mock_llm.validate({"messages": h.build_messages("s", "t", summary, recent)})
    valid = True
except ValueError as err:
    valid = str(err)
check("compaction keeps a valid message order around follow-up prompts",
      len(history) == 17 and history[-h.KEEP_RECENT]["role"] == "user"
      and recent[0]["role"] == "assistant" and len(recent) == 7 and valid is True, str(valid))

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
                       env={**os.environ, "SMOKE_PROMPT": "[scenario:basic] smoke",
                            "SMOKE_THINKING_PROMPT": "[scenario:blank] thinking probe"})
check("smoke_test.py", smoke.returncode == 0 and smoke.stdout.startswith("OK write_file"),
      smoke.stdout + smoke.stderr)
check("smoke test proves each thinking fragment switches the model",
      "thinking off: 0 reasoning characters" in smoke.stdout
      and "thinking on: 32 reasoning characters" in smoke.stdout
      and "thinking max: 32 reasoning characters" in smoke.stdout, smoke.stdout + smoke.stderr)
broken = subprocess.run(
    [sys.executable, str(ROOT / "harness" / "smoke_test.py")], capture_output=True, text=True,
    timeout=60, env={**os.environ, "SMOKE_PROMPT": "[scenario:basic] smoke again",
                     "SMOKE_THINKING_PROMPT": "[scenario:blank] dead switch",
                     "LLM_THINKING": json.dumps({"on": {"enable_thinking": True}})})
check("smoke test fails when a fragment does nothing",
      broken.returncode != 0 and "did not switch thinking" in broken.stderr, broken.stderr[-200:])

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
