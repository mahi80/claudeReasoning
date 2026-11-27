"""server.py - HTMX chat UI in front of the harness, with on-demand GPU start.

Run from the repository root:
    uvicorn server:app --app-dir app --host 127.0.0.1 --port 8080
There is no login here. Keep it on localhost or put it behind your own authentication.
"""
from __future__ import annotations

import html
import json
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

import mini_harness as h  # noqa: E402
import pod_manager  # noqa: E402

APPROVAL_TIMEOUT = float(os.environ.get("APPROVAL_TIMEOUT", "300"))   # seconds
EFFORT_LABELS = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "Extra high",
                 "max": "Max"}
Level = Literal["low", "medium", "high", "xhigh", "max"]

TOOLS = list(h.ORCHESTRATOR_TOOLS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if h.MCP_CONFIG:
        import mcp_bridge
        TOOLS.extend(mcp_bridge.load_config(h.MCP_CONFIG))
    try:
        yield
    finally:
        if h.MCP_CONFIG:
            mcp_bridge.close()
            TOOLS[:] = h.ORCHESTRATOR_TOOLS


app = FastAPI(title="Agent chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
RUNS: dict[str, "Run"] = {}


class Run:
    """One user request: its event log and at most one pending approval."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.events: list[tuple[str, str]] = []      # (event name, HTML fragment)
        self.changed = threading.Condition()
        self.finished = False
        self.decision = False
        self.answered = threading.Event()
        self.approval_lock = threading.Lock()
        self.pending_approval: str | None = None
        self.approval_deadline = 0.0

    def emit(self, event: str, fragment: str, last: bool = False) -> None:
        with self.changed:
            self.events.append((event, fragment))
            self.finished = self.finished or last
            self.changed.notify_all()

    def ask(self, name: str, args: dict) -> bool:
        if not self.approval_lock.acquire(timeout=h.time_left(APPROVAL_TIMEOUT)):
            h.time_left(APPROVAL_TIMEOUT)
            return False
        try:
            approval_id = uuid.uuid4().hex
            wait_seconds = h.time_left(APPROVAL_TIMEOUT)
            with self.changed:
                self.answered.clear()
                self.decision = False
                self.pending_approval = approval_id
                self.approval_deadline = time.monotonic() + wait_seconds
            buttons = "".join(
                f'<button hx-post="/runs/{self.id}/approval/{approval_id}/{choice}" '
                f'hx-target="closest .approval-request" hx-swap="innerHTML">{label}</button>'
                for choice, label in (("allow", "Approve"), ("deny", "Deny")))
            detail = html.escape(str(args.get("command") or json.dumps(args)))
            tool = html.escape(name)
            self.emit("approval", f'<div class="approval-request" id="approval-{approval_id}">'
                                  f"<p>The agent wants to use <code>{tool}</code>:"
                                  f"<br><code>{detail}</code></p>{buttons}</div>")
            answered = self.answered.wait(h.time_left(APPROVAL_TIMEOUT))
            h.time_left(APPROVAL_TIMEOUT)
            with self.changed:
                return answered and self.decision
        finally:
            with self.changed:
                self.pending_approval = None
            self.emit("approval", "<span></span>")
            self.approval_lock.release()


def current_run() -> Run | None:
    return RUNS.get(h.RUN_ID.get())


def on_trace(record: dict) -> None:
    """Turn harness trace events into status lines for the run they belong to."""
    run = RUNS.get(record["run"])
    if run is None:
        return
    if record["event"] == "model" and record["tool_calls"]:
        who = {"worker": "Worker", "reviewer": "Reviewer"}.get(record["agent"], "Agent")
        tools = html.escape(", ".join(record["tool_calls"]))
        run.emit("status", f"{who} step {record['step']}: {tools}")
    elif record["event"] == "review":
        verdict = "passed" if record["passed"] else "changes requested"
        run.emit("status", f"Independent review: {verdict}")
    elif record["event"] == "plan":
        run.emit("plan", html.escape(record["plan"]).replace("\n", "<br>"))
    elif record["event"] == "compact":
        run.emit("status", "Summarising earlier steps to free context")
    elif record["event"] == "worker_start":
        run.emit("status", f"Delegating to worker: {html.escape(', '.join(record['tools']))}")
    elif record["event"] == "budget_limit":
        run.emit("status", f"Execution stopped: {html.escape(record['reason'])}")


h.LISTENERS.append(on_trace)
h.ask_operator = lambda name, args: bool(current_run() and current_run().ask(name, args))


def work(run: Run, message: str, effort: str) -> None:
    """Background thread: make sure the GPU is up, then run the agent loop."""
    h.RUN_ID.set(run.id)
    try:
        pod_manager.ensure_ready(lambda text: run.emit("status", html.escape(text)))
        run.emit("status", f"Working at {EFFORT_LABELS[effort].lower()} effort")
        answer = h.run_agent(message, h.orchestrator_system(), TOOLS,
                             effort=effort)
        run.emit("answer", html.escape(answer).replace("\n", "<br>"))   # never raw HTML
    except Exception as err:
        failure = html.escape(f"{type(err).__name__}: {err}")
        run.emit("answer", f'<span class="error">Run failed. {failure}</span>')
    finally:
        pod_manager.touch()
        run.emit("status", "<span></span>")
        run.emit("approval", "<span></span>")
        run.emit("done", "ok", last=True)


def active_runs() -> int:
    return sum(not run.finished for run in RUNS.values())


if pod_manager.POD_ID:
    pod_manager.start_watchdog(active_runs,
                               every=float(os.environ.get("POD_WATCH_SECONDS", "60")))

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent chat</title>
<script src="/static/htmx.min.js"></script>
<script src="/static/sse.min.js"></script>
<style>
  body { font: 16px/1.5 system-ui, sans-serif; margin: 0; background: #f5f6f8; color: #1c2733; }
  main { max-width: 760px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 20px; }
  .msg { padding: 10px 14px; border-radius: 10px; margin: 10px 0; overflow-wrap: anywhere; }
  .user { background: #1f3a5f; color: #fff; margin-left: 15%; }
  .agent { background: #fff; border: 1px solid #d5dbe3; margin-right: 15%; }
  .status { color: #5b6573; font-size: 14px; }
  .plan:not(:empty) { font-size: 14px; border-left: 3px solid #c3cad4; padding-left: 10px;
                      margin-bottom: 8px; }
  .approval:not(:empty) { margin-top: 6px; }
  .approval button { margin-right: 8px; padding: 6px 14px; }
  .error { color: #a12626; }
  form { display: flex; gap: 8px; position: sticky; bottom: 0; padding: 12px 0;
         background: #f5f6f8; }
  input { flex: 1; min-width: 0; padding: 10px; font-size: 16px; border: 1px solid #c3cad4;
          border-radius: 8px; }
  select { padding: 10px 4px; font-size: 16px; border: 1px solid #c3cad4;
           border-radius: 8px; background: #fff; color: inherit; }
  button { padding: 10px 16px; font-size: 16px; border: 0; border-radius: 8px;
           background: #1f3a5f; color: #fff; }
</style></head>
<body hx-ext="sse"><main>
<h1>Agent chat</h1>
<div id="messages"></div>
<form hx-post="/chat" hx-target="#messages" hx-swap="beforeend"
      hx-on::after-request="this.elements.message.value = ''">
  <input name="message" placeholder="Give the agent a task" required autofocus>
  <select name="effort" aria-label="Effort">__EFFORTS__</select>
  <button>Send</button>
</form>
</main></body></html>""".replace("__EFFORTS__", "".join(
    f'<option value="{value}"{" selected" if value == "medium" else ""}>{label}</option>'
    for value, label in EFFORT_LABELS.items()))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


@app.post("/chat", response_class=HTMLResponse)
def chat(message: str = Form(...), effort: Level = Form("medium")) -> str:
    """Start a run and return the two chat bubbles; the second listens for events."""
    run = Run()
    RUNS[run.id] = run
    threading.Thread(target=work, args=(run, message, effort), daemon=True).start()
    return (f'<div class="msg user">{html.escape(message)}</div>'
            f'<div class="msg agent" sse-connect="/runs/{run.id}/events" sse-close="done">'
            '<div class="plan" sse-swap="plan"></div>'
            '<div class="status" sse-swap="status">Queued</div>'
            '<div class="approval" sse-swap="approval"></div>'
            '<div class="answer" sse-swap="answer"></div></div>')


@app.get("/runs/{run_id}/events")
def events(run_id: str) -> StreamingResponse:
    """Server-sent events for one run. A reconnecting browser gets the log replayed."""
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")

    def stream():
        sent = 0
        while True:
            with run.changed:
                if len(run.events) == sent and not run.finished:
                    run.changed.wait(timeout=15)
                batch, finished = run.events[sent:], run.finished
            if not batch and not finished:
                yield ": keep-alive\n\n"          # keeps idle proxies from closing us
                continue
            for event, fragment in batch:
                data = "\n".join("data: " + line for line in fragment.split("\n"))
                yield f"event: {event}\n{data}\n\n"
            sent += len(batch)
            if finished and sent == len(run.events):
                return

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


@app.post("/runs/{run_id}/approval/{approval_id}/{choice}", response_class=HTMLResponse)
def approval(run_id: str, approval_id: str, choice: Literal["allow", "deny"]) -> str:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    with run.changed:
        if (run.pending_approval != approval_id
                or time.monotonic() >= run.approval_deadline):
            raise HTTPException(409, "approval is no longer pending")
        run.decision = choice == "allow"
        run.pending_approval = None
        run.answered.set()
        return "Approved" if run.decision else "Denied"
