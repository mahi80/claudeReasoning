"""mini_harness.py - reference agent harness for an OpenAI-compatible endpoint (vLLM).

One loop, a tool registry, subagents, skills, context compaction and tracing.
Set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL to point it at your model server.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openai import OpenAI

# ---------------------------------------------------------------- configuration
BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
API_KEY = os.environ.get("LLM_API_KEY", "EMPTY")
MODEL = os.environ.get("LLM_MODEL", "agent-model")
WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "workspace")).resolve()
SKILLS_DIR = Path(os.environ.get("AGENT_SKILLS", "skills")).resolve()
TRACE_FILE = Path(os.environ.get("AGENT_TRACE", "trace.jsonl"))
CHECKPOINT_DIR = Path(os.environ.get("AGENT_CHECKPOINTS", "checkpoints"))
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "0"))            # 0: effort preset
CONTEXT_BUDGET = int(os.environ.get("AGENT_CONTEXT_BUDGET", "24000"))  # prompt tokens
CONTEXT_WINDOW = int(os.environ.get("LLM_CONTEXT_WINDOW", "32768"))    # --max-model-len
AUTO_APPROVE = os.environ.get("AGENT_AUTO_APPROVE", "0") == "1"
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))      # see the model card
EXTRA_BODY = json.loads(os.environ.get("LLM_EXTRA_BODY", "{}"))    # sent on every call
THINKING = json.loads(os.environ.get("LLM_THINKING", "{}"))        # off / on / max / brief
THINKING_SCOPE = os.environ.get("LLM_THINKING_SCOPE", "step")      # step | task
KEEP_REASONING = os.environ.get("LLM_KEEP_REASONING", "0") == "1"
MAX_TOOL_CHARS = 6000   # tool output handed back to the model
KEEP_RECENT = 8         # messages kept word for word when compacting

client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=600)
RUN_ID = contextvars.ContextVar("run_id", default="-")   # set by the caller per request
LISTENERS: list[Callable[[dict], None]] = []             # e.g. a UI showing live progress


def trace(event: str, **data) -> None:
    """Append one JSON line per event. This file is the audit trail."""
    record = {"ts": round(time.time(), 3), "run": RUN_ID.get(), "event": event, **data}
    with TRACE_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    for listener in LISTENERS:
        listener(record)


# ---------------------------------------------------------------- effort levels
@dataclass(frozen=True)
class Effort:
    """One preset: how hard the harness lets the model work on a task."""
    name: str
    thinking: str      # off | key (first step, and after a failed tool call) | all | max
    max_steps: int
    max_tokens: int    # per model call, thinking included
    workers: int       # worker agents one run may start
    verify: bool       # one self-check before an answer is accepted
    reviews: int       # independent reviews; a failed review costs one more attempt


EFFORTS = {e.name: e for e in (
    Effort("low", "off", 8, 4096, 0, False, 0),
    Effort("medium", "key", 20, 4096, 2, False, 0),
    Effort("high", "all", 40, 8192, 4, True, 0),
    Effort("xhigh", "all", 80, 8192, 6, True, 1),
    Effort("max", "max", 150, 16384, 8, True, 2),
)}
LADDER = list(EFFORTS)
GUIDANCE = {   # the behavioural half of a level: one line added to every system prompt
    "low": "Effort: low. Take the shortest route to a correct result. Skip planning for "
           "simple work and do nothing beyond what was asked.",
    "medium": "Effort: medium. Plan briefly, then act. Check what is cheap to check.",
    "high": "Effort: high. Plan before you act and check each result before you rely "
            "on it.",
    "xhigh": "Effort: extra high. Weigh alternatives before you commit, test edge cases "
             "and confirm every claim with a tool before you answer.",
    "max": "Effort: maximum. Be exhaustive. Break the problem down fully, question "
           "your own assumptions and verify the result in more than one way before you "
           "answer.",
}
BUDGET = contextvars.ContextVar("budget", default=None)   # per run: effort, workers


def budgets(effort: Effort) -> tuple[int, int]:
    """(max_tokens, prompt budget): a longer reply leaves less room for history."""
    max_tokens = min(effort.max_tokens, CONTEXT_WINDOW // 2)
    return max_tokens, min(CONTEXT_BUDGET, CONTEXT_WINDOW - max_tokens - 4096)


def thinking_mode(effort: Effort, step: int, turns: list[dict]) -> str:
    """Which LLM_THINKING fragment this one call gets: off, on, brief or max.

    'key' pays for thinking only where it matters most: the first step, and the step
    after a tool call failed. Not every model can change mid-task: with its reasoning
    kept in the history, Gemma 4 goes on thinking after one step that thought. For those
    set LLM_THINKING_SCOPE=task. 'key' is then one choice for the whole task: the
    'brief' fragment if you defined one (thinking with a budget), otherwise 'on'.
    """
    mode = effort.thinking
    if mode == "key" and THINKING_SCOPE == "task":
        mode = "brief" if "brief" in THINKING else "on"
    elif mode == "key":
        results = []
        for message in reversed(turns):               # the newest batch of tool results
            if message["role"] != "tool":
                break
            results.append(message["content"])
        stuck = any(r.startswith(("ERROR", "DENIED")) for r in results)
        mode = "on" if step == 1 or stuck else "off"
    elif mode == "all" or (mode == "max" and "max" not in THINKING):
        mode = "on"
    return mode


# ---------------------------------------------------------------- tool registry
@dataclass
class Tool:
    name: str
    description: str             # the routing logic: what it does and when to use it
    parameters: dict             # JSON schema
    fn: Callable[..., str]
    needs_approval: bool = False
    parallel: bool = False       # safe to run next to other calls in the same turn
    strict: bool = True          # ask the server to constrain arguments to the schema
    max_chars: int = MAX_TOOL_CHARS

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters, "strict": self.strict}}


REGISTRY: dict[str, Tool] = {}


def obj(**props: str) -> dict:
    """Strict-style schema: string fields, all required, nothing extra allowed."""
    fields = {k: {"type": "string", "description": v} for k, v in props.items()}
    return {"type": "object", "additionalProperties": False,
            "required": list(props), "properties": fields}


def tool(name: str, description: str, parameters: dict, **options):
    def register(fn):
        REGISTRY[name] = Tool(name, description, parameters, fn, **options)
        return fn
    return register


# ---------------------------------------------------------------- built-in tools
def inside_workspace(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents:
        raise PermissionError(f"{path} is outside the workspace")
    return p


@tool("read_file", "Read a text file from the workspace. Use it before editing a file "
      "or whenever you need a file's contents. Long files come back clipped.",
      obj(path="Path relative to the workspace root"), parallel=True)
def read_file(path: str) -> str:
    return inside_workspace(path).read_text(errors="replace")


@tool("write_file", "Create a new text file in the workspace, or replace a whole file. "
      "For a small change to an existing file use edit_file instead.",
      obj(path="Path relative to the workspace root", content="Full text of the file"))
def write_file(path: str, content: str) -> str:
    p = inside_workspace(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} characters to {path}"


@tool("edit_file", "Replace one exact snippet in an existing file. old_text must occur "
      "exactly once, so read the file first and copy the snippet from it.",
      obj(path="Path relative to the workspace root", old_text="Exact text to replace",
          new_text="Text to put in its place"))
def edit_file(path: str, old_text: str, new_text: str) -> str:
    p = inside_workspace(path)
    text = p.read_text()
    if text.count(old_text) != 1:
        return f"ERROR: old_text matched {text.count(old_text)} times; it must match once"
    p.write_text(text.replace(old_text, new_text))
    return f"edited {path}"


@tool("list_dir", "List the files and folders directly under a workspace path. "
      "Use it to find your way around before reading files.",
      obj(path="Folder relative to the workspace root; use . for the root"),
      parallel=True)
def list_dir(path: str) -> str:
    entries = sorted(inside_workspace(path).iterdir())
    return "\n".join(e.name + ("/" if e.is_dir() else "") for e in entries) or "(empty)"


READ_ONLY = {"ls", "cat", "head", "tail", "grep", "wc", "pwd", "diff"}


def is_read_only(command: str) -> bool:
    """One allow-listed command, no shell operators, no path leaving the workspace."""
    if re.search(r"[;&|`$<>\n]", command):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    escapes = any(w.startswith(("/", "~")) or ".." in w for w in words[1:])
    return bool(words) and words[0] in READ_ONLY and not escapes


@tool("run_shell", "Run one shell command in the workspace and return its exit code and "
      "output. Use it for tests, builds and searches. Read-only commands run at once; "
      "anything else needs operator approval.",
      obj(command="The command line to run"), needs_approval=True)
def run_shell(command: str) -> str:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(WORKSPACE)}   # no secrets
    done = subprocess.run(command, shell=True, cwd=WORKSPACE, env=env,
                          capture_output=True, text=True, timeout=120)
    return f"exit={done.returncode}\n{done.stdout}{done.stderr}"


def no_operator(name: str, args: dict) -> bool:
    """Nobody is there to ask, so the answer is no."""
    return False


ask_operator = no_operator        # replace with a UI prompt or a policy engine


def unattended() -> bool:
    """True when an action that needs approval has nobody to approve it."""
    return ask_operator is no_operator and not AUTO_APPROVE


UNATTENDED = (
    "Nobody is available to approve commands in this run. run_shell only runs these "
    f"read-only commands: {', '.join(sorted(READ_ONLY))}. It cannot run programs or change "
    "anything. To create or change files use write_file and edit_file; write_file creates "
    "missing folders.")


def approved(t: Tool, args: dict) -> bool:
    if not t.needs_approval or AUTO_APPROVE:
        return True
    if t.name == "run_shell" and is_read_only(str(args.get("command", ""))):
        return True
    return ask_operator(t.name, args)


def denial(t: Tool) -> str:
    """What the model is told. Without an operator, also what to do instead."""
    if not unattended():
        return "DENIED: the operator did not approve this action. Continue without it."
    instead = (" Read-only commands still run. To create or change files use write_file "
               "or edit_file.") if t.name == "run_shell" else ""
    return (f"DENIED: nobody is available to approve {t.name} in this run, so do not "
            f"try it again.{instead}")


# ---------------------------------------------------------------- skills
def skills_index() -> str:
    """One line per skill for the system prompt. Full text loads only on demand."""
    lines = []
    for f in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        parts = f.read_text().split("---")
        meta = dict(line.split(":", 1) for line in parts[1].splitlines() if ":" in line) \
            if len(parts) > 2 else {}
        lines.append(f"- {f.parent.name}: {meta.get('description', '').strip()}")
    return "\n".join(lines) or "(none installed)"


@tool("load_skill", "Load the full instructions of a skill listed in the system prompt. "
      "Call it before you start any work that a listed skill covers.",
      obj(name="Skill name exactly as listed"), parallel=True, max_chars=20000)
def load_skill(name: str) -> str:
    f = (SKILLS_DIR / name / "SKILL.md").resolve()
    if SKILLS_DIR not in f.parents or not f.exists():
        return f"ERROR: no skill named '{name}'"
    return f.read_text()


# ---------------------------------------------------------------- model call
@dataclass
class Reply:
    text: str
    calls: list[dict]
    thought: str = ""          # the model's reasoning, when the server separates it
    prompt_tokens: int = 0
    output_tokens: int = 0     # thinking included


def call_model(messages: list[dict], tools: list[Tool], max_tokens: int = 4096,
               extras: dict | None = None) -> Reply:
    """One streamed completion.

    Streaming keeps bytes flowing, which matters behind proxies that drop idle
    connections (Runpod's HTTP proxy closes them after 100 seconds).
    """
    body = dict(EXTRA_BODY)
    for key, value in (extras or {}).items():          # merge nested dicts one level deep
        both = isinstance(value, dict) and isinstance(body.get(key), dict)
        body[key] = {**body[key], **value} if both else value
    kwargs = dict(model=MODEL, messages=messages, temperature=TEMPERATURE,
                  max_tokens=max_tokens, stream=True,
                  stream_options={"include_usage": True}, extra_body=body)
    if tools:
        kwargs.update(tools=[t.schema() for t in tools], tool_choice="auto")
    reply, text, thought, calls = Reply("", []), [], [], {}
    for chunk in client.chat.completions.create(**kwargs):
        if chunk.usage:
            reply.prompt_tokens = chunk.usage.prompt_tokens
            reply.output_tokens = chunk.usage.completion_tokens or 0
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            text.append(delta.content)
        thought.append(getattr(delta, "reasoning", None)      # vLLM's field name, and
                       or getattr(delta, "reasoning_content", None) or "")   # its old one
        for tc in delta.tool_calls or []:
            slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            slot["id"] = tc.id or slot["id"]
            if tc.function:
                slot["name"] += tc.function.name or ""
                slot["arguments"] += tc.function.arguments or ""
    reply.calls = [calls[i] for i in sorted(calls)]
    for c in reply.calls:
        c["id"] = c["id"] or uuid.uuid4().hex[:9]
    reply.text, reply.thought = "".join(text), "".join(thought)
    return reply


# ---------------------------------------------------------------- tool execution
def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    cut = len(text) - limit
    return f"{text[:half]}\n...[{cut} characters clipped]...\n{text[-half:]}"


def execute(call: dict, allowed: dict[str, Tool], seen: Counter) -> str:
    """Run one tool call. Every failure returns text the model can act on."""
    name, raw = call["name"], call["arguments"] or "{}"
    if name not in allowed:
        return f"ERROR: unknown tool '{name}'. Available: {', '.join(sorted(allowed))}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
    except ValueError as err:
        return f"ERROR: arguments are not valid JSON ({err}). Send the call again."
    fingerprint = name + hashlib.sha1(raw.encode()).hexdigest()
    seen[fingerprint] += 1
    if seen[fingerprint] > 2:
        return ("ERROR: this exact call has already run twice. "
                "Try a different approach or give your final answer.")
    t = allowed[name]
    if not approved(t, args):
        return denial(t)
    try:
        return clip(str(t.fn(**args)), t.max_chars)
    except TypeError as err:
        fields = t.parameters.get("required")
        return f"ERROR: wrong arguments ({err}). Expected fields: {fields}"
    except Exception as err:   # report, never crash the loop
        return f"ERROR: {type(err).__name__}: {err}"


# ---------------------------------------------------------------- context control
def build_messages(system: str, task: str, summary: str, turns: list[dict],
                   plan: str = "") -> list[dict]:
    user = task
    if plan:                      # pinned: survives compaction because it is re-read
        user += f"\n\n[Current plan]\n{plan}"
    if summary:
        user += f"\n\n[Summary of your earlier work]\n{summary}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}] + turns


def compact(turns: list[dict], summary: str) -> tuple[list[dict], str]:
    """Fold older turns into a model-written summary; keep recent turns verbatim."""
    old, recent = turns[:-KEEP_RECENT], turns[-KEEP_RECENT:]
    while recent and recent[0]["role"] != "assistant":   # never orphan a tool result,
        old.append(recent.pop(0))                        # never open on a user nudge
    if not old:
        return turns, summary
    lines = [m["role"] + ": "
             + clip(json.dumps(m.get("tool_calls") or m.get("content")), 1500)
             for m in old]
    prompt = ("Summarise this agent transcript for the agent itself. Keep decisions, "
              "file paths, results and open items. Be brief.\n\n"
              + (f"Earlier summary: {summary}\n\n" if summary else "") + "\n".join(lines))
    new_summary = call_model([{"role": "user", "content": prompt}], []).text
    trace("compact", folded=len(old), kept=len(recent))
    return recent, new_summary


# ---------------------------------------------------------------- long tasks
def plan_path() -> Path:
    return inside_workspace(f".agent/plan-{RUN_ID.get()}.md")


@tool("update_plan", "Save or replace your working plan as a short checklist: the steps, "
      "which are done, what is next, key decisions. Use it at the start of any task that "
      "needs more than a few steps, and again whenever the plan changes. The saved plan "
      "is shown to you on every turn, even after older turns have been summarised.",
      obj(plan="The whole plan, one step per line, finished steps marked [x]"))
def update_plan(plan: str) -> str:
    path = plan_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan)
    trace("plan", plan=plan)
    return "plan saved"


def checkpoint_file(task: str) -> Path:
    """One file per run id, or per task text when no run id was set."""
    run = RUN_ID.get()
    key = run if run != "-" else hashlib.sha1(task.encode()).hexdigest()[:12]
    return CHECKPOINT_DIR / f"{key}.json"


def save_checkpoint(task: str, summary: str, turns: list[dict]) -> None:
    """Called after every finished step, so a crash or a stopped pod loses one step."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    target = checkpoint_file(task)
    draft = target.with_suffix(".tmp")
    draft.write_text(json.dumps({"task": task, "summary": summary, "turns": turns}))
    draft.replace(target)         # atomic swap: never a half-written checkpoint


# ---------------------------------------------------------------- reasoning scaffolds
@tool("think", "Write down your reasoning before you act. It changes nothing and fetches "
      "nothing. Use it to work through a surprising tool result, weigh options, or check "
      "a plan against the task when the next step is not obvious.",
      obj(thought="Your reasoning, in a few sentences"), parallel=True)
def think(thought: str) -> str:
    return "noted"


VERIFY_PROMPT = (
    "Before this goes to the user, check it against the task. Use your tools to confirm "
    "anything you have not verified. If the answer is right and complete, reply with "
    "the single word CONFIRMED. If not, fix the problem, then give the full corrected "
    "answer.")

REVIEWER_SYSTEM = (
    "You are an independent reviewer. You did not do the work. Check the answer against "
    "the task, using your tools to inspect the workspace. Reply PASS on the first line "
    "if it fully meets the task. Otherwise reply FAIL on the first line, then list the "
    "specific problems.")

REJECTED = ("An independent reviewer rejected the answer:\n{verdict}\n\n"
            "Fix these problems, then give the full corrected answer.")


def review(task: str, answer: str, effort: str) -> str:
    """A second opinion from a fresh context that never saw how the answer was made."""
    brief = f"Task given to the agent:\n{task}\n\nAnswer it produced:\n{answer}"
    return run_agent(brief, REVIEWER_SYSTEM, ["read_file", "list_dir", "think"],
                     label="reviewer", effort=effort)


# ---------------------------------------------------------------- the loop
def run_agent(task: str, system: str, tool_names: list[str], label: str = "main",
              resume: bool = False, effort: str = "medium") -> str:
    """The whole agent: call the model, run the tools it asks for, repeat."""
    level, main = EFFORTS[effort], label == "main"
    allowed = {n: REGISTRY[n] for n in tool_names if n in REGISTRY}
    if "run_shell" in allowed and unattended():
        system = f"{system}\n\n{UNATTENDED}"      # or it learns one refusal at a time
    system = f"{system}\n\n{GUIDANCE[level.name]}"
    if level.thinking == "off":
        allowed.pop("think", None)                    # low effort: act, do not deliberate
    if main:
        BUDGET.set({"effort": level, "workers": 0})
        if level.workers == 0:
            allowed.pop("spawn_agent", None)          # and do not delegate
        trace("run", effort=level.name, resume=resume)
    limit = level.max_steps if main else min(level.max_steps, 40)
    limit = min(limit, MAX_STEPS) if MAX_STEPS else limit
    max_tokens, prompt_budget = budgets(level)
    verified, reviews = not (main and level.verify), level.reviews if main else 0
    turns, summary, seen, blank, draft = [], "", Counter(), False, ""
    planning = "update_plan" in allowed
    saved = checkpoint_file(task)
    if resume and saved.exists():
        state = json.loads(saved.read_text())
        turns, summary = state["turns"], state["summary"]
        trace("resume", agent=label, turns=len(turns))
    elif planning:
        plan_path().unlink(missing_ok=True)       # a new task starts without an old plan
    for step in range(1, limit + 1):
        plan = plan_path().read_text() if planning and plan_path().exists() else ""
        messages = build_messages(system, task, summary, turns, plan)
        mode = "off" if blank else thinking_mode(level, step, turns)
        reply = call_model(messages, list(allowed.values()), max_tokens,
                           THINKING.get(mode, {}))
        text, calls = reply.text, reply.calls
        trace("model", agent=label, step=step, prompt_tokens=reply.prompt_tokens,
              output_tokens=reply.output_tokens, thinking=mode,
              reasoning_chars=len(reply.thought), tool_calls=[c["name"] for c in calls])
        if not calls and not text.strip() and not blank:
            blank = True              # thinking used the whole reply: retry without it
            trace("blank", agent=label, step=step)
            continue
        blank = False
        if not calls:
            if draft and text.strip().upper().startswith("CONFIRMED"):
                text = draft                          # the check kept the earlier answer
            nudge = ""
            if not verified:                          # self-check, once per run
                verified, nudge = True, VERIFY_PROMPT
            elif reviews:                             # second opinion, fresh context
                reviews -= 1
                verdict = review(task, text, level.name).strip()
                failed = verdict.upper().startswith("FAIL")   # anything else: accept
                trace("review", passed=not failed)
                reviews = reviews if failed else 0
                nudge = REJECTED.format(verdict=clip(verdict, 2000)) if failed else ""
            if not nudge:
                return text                           # plain answer = finished
            draft = text
            turns += [{"role": "assistant", "content": text or "(no answer)"},
                      {"role": "user", "content": nudge}]
            continue
        turn = {"role": "assistant", "content": text or None, "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls]}
        if KEEP_REASONING and reply.thought:
            turn["reasoning"] = reply.thought         # thoughts stay between tool calls
        turns.append(turn)
        run = lambda c: execute(c, allowed, seen)
        if len(calls) > 1 and all(c["name"] in allowed and allowed[c["name"]].parallel
                                  for c in calls):
            with ThreadPoolExecutor(max_workers=4) as pool:   # e.g. several subagents
                jobs = [pool.submit(contextvars.copy_context().run, run, c)
                        for c in calls]
                results = [job.result() for job in jobs]
        else:
            results = [run(c) for c in calls]         # order may matter: one by one
        for c, result in zip(calls, results):
            trace("tool", agent=label, step=step, tool=c["name"], chars=len(result),
                  failed=result.startswith(("ERROR", "DENIED")))
            turns.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        if reply.prompt_tokens > prompt_budget:
            turns, summary = compact(turns, summary)
        if main:
            save_checkpoint(task, summary, turns)
    trace("step_limit", agent=label)
    return f"Stopped at the {limit}-step limit before finishing. {summary}".strip()


def run_escalating(task: str, system: str, tool_names: list[str], start: str = "low",
                   accept: Callable[[str], bool] = lambda answer: True) -> str:
    """Start cheap and climb one level whenever a run stalls or its answer is rejected."""
    answer = ""
    for name in LADDER[LADDER.index(start):]:
        stalled = answer.startswith("Stopped at")     # a stalled run resumes
        answer = run_agent(task, system, tool_names, effort=name, resume=stalled)
        if not answer.startswith("Stopped at") and accept(answer):
            break
        trace("escalate", after=name)
    return answer


# ---------------------------------------------------------------- subagents
WORKER_TOOLS = ["read_file", "write_file", "edit_file", "list_dir", "run_shell",
                "load_skill", "think"]
ORCHESTRATOR_TOOLS = WORKER_TOOLS + ["spawn_agent", "update_plan"]

SPAWN_LOCK = threading.Lock()

WORKER_SYSTEM = (
    "You are a worker agent. Complete the single task you are given using your tools. "
    "You cannot ask questions, so make sensible assumptions and state them. Finish "
    "with a short report: what you did, what you found, and anything left unresolved.")


@tool("spawn_agent", "Hand one self-contained sub-task to a fresh worker agent with its "
      "own empty context. Use it for independent pieces of work that can run side by "
      "side, or for heavy reading where you only need the conclusion. The worker sees "
      "nothing of this conversation, so put every detail it needs in the task. To run "
      "several workers in parallel, call this tool several times in one turn. Do not use "
      "it for work you can finish yourself in one or two tool calls.",
      obj(task="Complete brief for the worker: goal, inputs, constraints, report wanted"),
      parallel=True)
def spawn_agent(task: str) -> str:
    budget = BUDGET.get() or {"effort": EFFORTS["medium"], "workers": 0}
    with SPAWN_LOCK:                                  # parallel calls share one budget
        if budget["workers"] >= budget["effort"].workers:
            return (f"ERROR: this effort level allows {budget['effort'].workers} worker "
                    "agents and they are used up. Do the remaining work yourself.")
        budget["workers"] += 1
    return run_agent(task, WORKER_SYSTEM, WORKER_TOOLS, label="worker",
                     effort=budget["effort"].name)    # no spawn tool here: no nesting


def orchestrator_system() -> str:
    return f"""You are an agent that completes tasks by calling tools.

How to work:
- For a task with more than a few steps, save a checklist with update_plan first. Tick
  steps off as you finish them and change the plan when the facts change.
- Split the task into parts. Do dependent parts in order. If you have spawn_agent, hand
  independent parts to it, all in one turn, so they run in parallel.
- Do small things yourself. Delegating costs a full briefing.
- Read before you edit. Check a result before you report it.
- When a result surprises you and you have the think tool, reason it through there
  before the next call.
- If a tool returns ERROR, fix the call or change approach. Never repeat it unchanged.
- When finished, reply in plain text: what you did and what is left.

Skills (call load_skill before work that one covers):
{skills_index()}"""


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description="Run one task through the agent loop.")
    cli.add_argument("task", nargs="+")
    cli.add_argument("--effort", choices=LADDER, default="medium")
    cli.add_argument("--resume", action="store_true", help="continue from the checkpoint")
    cli.add_argument("--escalate", action="store_true",
                     help="start at --effort and climb a level each time a run stalls")
    args = cli.parse_args()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    prompt, system = " ".join(args.task), orchestrator_system()
    if args.escalate:
        print(run_escalating(prompt, system, ORCHESTRATOR_TOOLS, start=args.effort))
    else:
        print(run_agent(prompt, system, ORCHESTRATOR_TOOLS, resume=args.resume,
                        effort=args.effort))
