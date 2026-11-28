"""server.py - HTMX chat UI in front of the harness, with on-demand GPU start.

Run from the repository root:
    uvicorn server:app --app-dir app --host 127.0.0.1 --port 8080
Set AGENT_CHAT_AUTH_CONFIG to an operator-owned single-tenant access configuration.
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

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from access import Access, Principal
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))

import mini_harness as h  # noqa: E402
import pod_manager  # noqa: E402
import coding  # noqa: E402
import delivery_tools  # noqa: E402
import integrations  # noqa: E402

INTEGRATIONS_CONFIG = os.environ.get("AGENT_INTEGRATIONS_CONFIG", "")
CODING_CONFIG = os.environ.get("AGENT_DELIVERY_CONFIG", "")
WORKSPACE_LOCK = threading.Lock()
ACCESS = Access()
EXTRA_TOOLS: list[str] = []

APPROVAL_TIMEOUT = float(os.environ.get("APPROVAL_TIMEOUT", "300"))   # seconds
EFFORT_LABELS = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "Extra high",
                 "max": "Max"}
Level = Literal["low", "medium", "high", "xhigh", "max"]

TOOLS = list(h.ORCHESTRATOR_TOOLS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ACCESS.configure(os.environ.get("AGENT_CHAT_AUTH_CONFIG", ""), h.WORKSPACE)
        if CODING_CONFIG:
            coding.configure(CODING_CONFIG)
        if h.MCP_CONFIG:
            import mcp_bridge
            EXTRA_TOOLS.extend(mcp_bridge.load_config(h.MCP_CONFIG))
        if INTEGRATIONS_CONFIG:
            EXTRA_TOOLS.extend(integrations.load_config(INTEGRATIONS_CONFIG))
        TOOLS.extend(EXTRA_TOOLS)
        yield
    finally:
        ACCESS.close()
        if h.MCP_CONFIG:
            import mcp_bridge
            mcp_bridge.close()
        if INTEGRATIONS_CONFIG:
            integrations.close()
        EXTRA_TOOLS.clear()
        TOOLS[:] = h.ORCHESTRATOR_TOOLS
        if CODING_CONFIG:
            delivery_tools.close()


app = FastAPI(title="Agent chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
RUNS: dict[str, "Run"] = {}


@app.middleware("http")
async def authorize(request: Request, call_next):
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "same-origin"}
    origin = f"{request.url.scheme}://{request.url.netloc}"
    if not ACCESS.origin:
        return JSONResponse({"detail": "Chat authentication is unavailable"}, status_code=503, headers=headers)
    if origin != ACCESS.origin:
        return JSONResponse({"detail": "Invalid chat origin"}, status_code=400, headers=headers)
    public = request.url.path == "/login" or request.url.path.startswith("/static/")
    credentials = ACCESS.authenticate(request.headers.get("authorization"), request.cookies.get(ACCESS.cookie))
    if not public and credentials is None:
        if request.url.path == "/" and request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303, headers=headers)
        return JSONResponse({"detail": "Authentication required"}, status_code=401,
                            headers={**headers, "WWW-Authenticate": "Bearer"})
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if (request.url.path == "/login" or credentials is None or credentials[2]) and request.headers.get("origin") != ACCESS.origin:
            return JSONResponse({"detail": "Same-origin browser request required"}, status_code=403, headers=headers)
    request.state.credentials = credentials
    response = await call_next(request)
    response.headers.update(headers)
    return response


LOGIN = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign in</title>
<style>body { font: 16px/1.5 system-ui; max-width: 420px; margin: 60px auto; padding: 20px; }
input, button { box-sizing: border-box; width: 100%; padding: 12px; margin: 8px 0; }
button { background: #1f3a5f; color: white; border: 0; border-radius: 8px; }</style></head>
<body><h1>Sign in to Agent chat</h1><p>Use the access token supplied by the operator.</p>
<form method="post" action="/login"><label for="access-token">Access token</label>
<input id="access-token" name="token" type="password" autocomplete="off" required autofocus>
<button>Sign in</button></form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN


@app.post("/login")
def login(token: str = Form("")):
    session = ACCESS.login(token)
    if session is None:
        return HTMLResponse(LOGIN.replace("<form", '<p role="alert">Invalid access token.</p><form'), status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(ACCESS.cookie, session, max_age=ACCESS.session_seconds, httponly=True,
                        secure=ACCESS.origin.startswith("https://"), samesite="strict", path="/")
    return response


@app.post("/logout")
def logout(request: Request):
    ACCESS.logout(request.cookies.get(ACCESS.cookie))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(ACCESS.cookie, httponly=True, secure=ACCESS.origin.startswith("https://"), samesite="strict")
    return response


class Run:
    """One user request: its event log and at most one pending approval."""

    def __init__(self, owner: Principal) -> None:
        self.owner = owner
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
            while True:
                answered = self.answered.wait(h.time_left(
                    max(0, self.approval_deadline - time.monotonic())))
                h.time_left(APPROVAL_TIMEOUT)
                if answered or time.monotonic() >= self.approval_deadline:
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
    elif record["event"] == "coding_stage":
        run.emit("status", f"Coding: {html.escape(record['stage'])}")
    elif record["event"] == "check":
        outcome = "passed" if record["exit"] == 0 else "did not pass"
        run.emit("status", f"Check {html.escape(record['name'])}: {outcome}")
    elif record["event"] == "coding_review":
        run.emit("status", "Coding review: " + ("passed" if record["passed"] else "rejected"))


h.LISTENERS.append(on_trace)
h.ask_operator = lambda name, args: bool(current_run() and current_run().ask(name, args))


def work(run: Run, message: str, effort: str, mode: str = "chat") -> None:
    h.RUN_ID.set(run.id)
    locked = False
    try:
        if CODING_CONFIG:
            locked = WORKSPACE_LOCK.acquire(blocking=False)
            if not locked:
                run.emit("status", "Waiting for the shared workspace")
                WORKSPACE_LOCK.acquire()
                locked = True
        pod_manager.ensure_ready(lambda text: run.emit("status", html.escape(text)))
        run.emit("status", f"Working at {EFFORT_LABELS[effort].lower()} effort")
        if mode == "coding":
            result = coding.run(message, effort=effort, extra_tools=tuple(EXTRA_TOOLS))
            answer = f"{result.status.capitalize()}\n\n{result.answer}"
            if result.checks:
                answer += "\n\nRequired checks:\n" + "\n".join(
                    f"{row['name']}: {'passed' if row['exit'] == 0 else 'did not pass'} "
                    f"(exit={row['exit']}, {row['seconds']}s)" for row in result.checks)
            if result.review:
                answer += "\n\nIndependent review:\n" + h.clip(result.review, 2000)
        else:
            answer = h.run_agent(message, h.orchestrator_system(), TOOLS, effort=effort)
        run.emit("answer", html.escape(answer).replace("\n", "<br>"))
    except Exception as err:
        detail = type(err).__name__ if mode == "coding" else f"{type(err).__name__}: {err}"
        run.emit("answer", f'<span class="error">Run failed. {html.escape(detail)}</span>')
    finally:
        if locked:
            WORKSPACE_LOCK.release()
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
  .session { padding: 0; justify-content: space-between; }
  .mode { display: flex; gap: 16px; }
  .mode input { flex: none; }
  form { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 0; background: #f5f6f8; }
  input { flex: 1; min-width: 0; padding: 10px; font-size: 16px; border: 1px solid #c3cad4;
          border-radius: 8px; }
  select { padding: 10px 4px; font-size: 16px; border: 1px solid #c3cad4;
           border-radius: 8px; background: #fff; color: inherit; }
  button { padding: 10px 16px; font-size: 16px; border: 0; border-radius: 8px;
           background: #1f3a5f; color: #fff; }
</style></head>
<body hx-ext="sse"><main>
<h1>Agent chat</h1>
<form class="session" method="post" action="/logout"><span>__IDENTITY__</span><button>Sign out</button></form>
<div id="messages"></div>
<form hx-post="/chat" hx-target="#messages" hx-swap="beforeend"
      hx-on::after-request="if(event.detail.successful) this.elements.message.value = ''">
  <div class="mode" style="flex-basis: 100%">__MODE__</div>
  <input name="message" aria-label="Task" placeholder="Give the agent a task" required autofocus>
  <select name="effort" aria-label="Effort">__EFFORTS__</select>
  <button>Send</button>
</form>
</main></body></html>""".replace("__EFFORTS__", "".join(
    f'<option value="{value}"{" selected" if value == "medium" else ""}>{label}</option>'
    for value, label in EFFORT_LABELS.items()))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> str:
    principal = request.state.credentials[0]
    modes = (f'<label><input type="radio" name="mode" value="coding" '
             f'{"checked" if CODING_CONFIG else "disabled"}> Coding</label>'
             f'<label><input type="radio" name="mode" value="chat" '
             f'{"" if CODING_CONFIG else "checked"}> General</label>')
    page = PAGE.replace("__MODE__", modes).replace("__IDENTITY__", html.escape(f"{principal.user} / {principal.tenant}"))
    if CODING_CONFIG:
        page = page.replace('value="medium" selected', 'value="medium"').replace(
            'value="high"', 'value="high" selected')
    return page


@app.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form(...), effort: Level = Form("medium"),
         mode: Literal["chat", "coding"] = Form("chat")) -> str:
    if not message.strip():
        raise HTTPException(422, "A task is required")
    if mode == "coding" and not CODING_CONFIG:
        raise HTTPException(503, "Coding requires operator-configured checks")
    run = Run(request.state.credentials[0])
    RUNS[run.id] = run
    threading.Thread(target=work, args=(run, message, effort, mode), daemon=True).start()
    return (f'<div class="msg user">{html.escape(message)}</div>'
            f'<div class="msg agent" sse-connect="/runs/{run.id}/events" sse-close="done">'
            '<div class="plan" sse-swap="plan"></div>'
            '<div class="status" sse-swap="status">Queued</div>'
            '<div class="approval" sse-swap="approval"></div>'
            '<div class="answer" sse-swap="answer"></div></div>')


def owned_run(request: Request, run_id: str) -> Run:
    run = RUNS.get(run_id)
    if run is None or run.owner != request.state.credentials[0]:
        raise HTTPException(404, "unknown run")
    return run


@app.get("/runs/{run_id}/events")
def events(request: Request, run_id: str) -> StreamingResponse:
    """Server-sent events for one run. A reconnecting browser gets the log replayed."""
    run = owned_run(request, run_id)
    principal, key, browser = request.state.credentials

    def stream():
        sent = 0
        while True:
            with run.changed:
                if len(run.events) == sent and not run.finished:
                    run.changed.wait(timeout=15)
                batch, finished = run.events[sent:], run.finished
            if ACCESS.principal(key, browser) != principal:
                yield 'event: answer\ndata: Session expired. <a href="/login">Sign in again</a>\n\nevent: done\ndata: ok\n\n'
                return
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
def approval(request: Request, run_id: str, approval_id: str, choice: Literal["allow", "deny"]) -> str:
    run = owned_run(request, run_id)
    with run.changed:
        if (run.pending_approval != approval_id
                or time.monotonic() >= run.approval_deadline):
            raise HTTPException(409, "approval is no longer pending")
        run.decision = choice == "allow"
        run.pending_approval = None
        run.answered.set()
        return "Approved" if run.decision else "Denied"
