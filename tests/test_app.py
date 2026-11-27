"""HTTP-level tests of the chat UI server, pod manager and approvals.

Uses the mock model endpoint and a mock Runpod API. Run: python tests/test_app.py
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("harness", "tests", "app"):
    sys.path.insert(0, str(ROOT / folder))

import mock_llm  # noqa: E402
import mock_runpod  # noqa: E402

llm_server, llm_port = mock_llm.start()
rp_server, rp_port = mock_runpod.start()
tmp = Path(tempfile.mkdtemp(prefix="harness-app-"))
os.environ.update(
    LLM_BASE_URL=f"http://127.0.0.1:{llm_port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
    AGENT_WORKSPACE=str(tmp / "workspace"), AGENT_SKILLS=str(tmp / "skills"),
    AGENT_TRACE=str(tmp / "trace.jsonl"), AGENT_CHECKPOINTS=str(tmp / "checkpoints"),
    RUNPOD_API=f"http://127.0.0.1:{rp_port}/v1", RUNPOD_POD_ID="pod123",
    RUNPOD_API_KEY="rp-key", LLM_HEALTH_URL=f"http://127.0.0.1:{rp_port}/health",
    POD_POLL_SECONDS="0.1", POD_IDLE_SECONDS="1.5", POD_WATCH_SECONDS="0.3",
    POD_START_TIMEOUT="20", APPROVAL_TIMEOUT="20")

import httpx  # noqa: E402
import uvicorn  # noqa: E402

import pod_manager  # noqa: E402
import server  # noqa: E402

server.h.WORKSPACE.mkdir(parents=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
web = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
threading.Thread(target=web.run, daemon=True).start()
while not web.started:
    time.sleep(0.05)
BASE = f"http://127.0.0.1:{port}"
STATE = mock_runpod.STATE
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def post_chat(message: str) -> tuple[str, str]:
    reply = httpx.post(f"{BASE}/chat", data={"message": message}, timeout=10)
    assert reply.status_code == 200, reply.text
    return re.search(r'sse-connect="/runs/(\w+)/events"', reply.text).group(1), reply.text


def read_events(run_id: str, on_event=None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    with httpx.stream("GET", f"{BASE}/runs/{run_id}/events", timeout=40) as reply:
        assert reply.status_code == 200
        assert reply.headers["content-type"].startswith("text/event-stream")
        event, data = None, []
        for line in reply.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
            elif line == "" and event:
                out.append((event, "\n".join(data)))
                if on_event:
                    on_event(event, "\n".join(data))
                if event == "done":
                    break
                event, data = None, []
    return out


def texts(events: list[tuple[str, str]], kind: str) -> list[str]:
    return [d for e, d in events if e == kind]


# 1. page loads with htmx wiring and local scripts
page = httpx.get(BASE + "/").text
check("index page", 'hx-post="/chat"' in page and 'hx-ext="sse"' in page
      and httpx.get(BASE + "/static/htmx.min.js").status_code == 200
      and httpx.get(BASE + "/static/sse.min.js").status_code == 200)

# 2. cold start: two requests at once start the pod exactly once and both finish
ids, logs = [], {}
for n in (1, 2):
    run_id, fragment = post_chat(f"[scenario:basic] ui cold {n}")
    ids.append(run_id)
threads = [threading.Thread(target=lambda r=r: logs.__setitem__(r, read_events(r))) for r in ids]
[t.start() for t in threads]
[t.join(40) for t in threads]
all_status = " | ".join(s for r in ids for s in texts(logs[r], "status"))
check("cold start: pod started once for two concurrent requests", STATE["starts"] == 1, str(STATE))
check("cold start: user sees GPU start and readiness",
      "Starting the GPU pod" in all_status and "Model server is ready" in all_status, all_status)
check("both runs answered", all(texts(logs[r], "answer") == ["DONE: hello"] for r in ids),
      str({r: texts(logs[r], "answer") for r in ids}))
check("step progress streamed", "Agent step 1: write_file" in all_status
      and "Agent step 2: read_file" in all_status, all_status)
check("stream ends with done and clears status",
      all(logs[r][-1] == ("done", "ok") and texts(logs[r], "status")[-1] == "<span></span>"
          for r in ids))

# 3. warm pod: no second start, no start message
run_id, _ = post_chat("[scenario:basic] ui warm")
warm = read_events(run_id)
check("warm pod is reused", STATE["starts"] == 1
      and not any("Starting the GPU pod" in s for s in texts(warm, "status")))

# 4. approvals in the chat: deny the first command, allow the second
clicks: list[str] = []


def click(event: str, data: str) -> None:
    if event == "approval" and "hx-post" in data:
        choice = "deny" if not clicks else "allow"
        url = re.search(r'hx-post="(/runs/\w+/approval/' + choice + ')"', data).group(1)
        clicks.append(httpx.post(BASE + url, timeout=10).text)


run_id, _ = post_chat("[scenario:denied] ui shell")
shell = read_events(run_id, click)
answer = texts(shell, "answer")[0]
parts = answer.split(" || ")
check("approval buttons shown with the command",
      any("rm -rf important" in d and "Approve" in d and "Deny" in d
          for d in texts(shell, "approval")))
check("deny then allow respected", clicks == ["Denied", "Approved"] and len(parts) == 3
      and parts[0].startswith("DENIED") and parts[1].startswith("exit=")
      and parts[2].startswith("exit=0"), f"{clicks} {answer}")

# 5. untrusted text is escaped on the way to the browser
run_id, fragment = post_chat("<script>alert(1)</script> [scenario:unknown] ui xss")
xss = read_events(run_id)
check("user and model text escaped", "<script>" not in fragment and "&lt;script&gt;" in fragment
      and "&#x27;delete_everything&#x27;" in texts(xss, "answer")[0])

# 6. unknown run and replay of a finished run
check("unknown run is 404", httpx.get(f"{BASE}/runs/nope/events").status_code == 404
      and httpx.post(f"{BASE}/runs/nope/approval/allow").status_code == 404)
replay = read_events(ids[0])
check("finished run replays for a reconnecting browser",
      texts(replay, "answer") == ["DONE: hello"] and replay[-1] == ("done", "ok"))

# 7. trace lines carry the run id
lines = [json.loads(x) for x in server.h.TRACE_FILE.read_text().splitlines()]
check("trace records carry run ids", {ids[0], ids[1]} <= {x["run"] for x in lines})

# 8. idle watchdog stops the pod, and the next request starts it again
deadline = time.time() + 10
while STATE["stops"] == 0 and time.time() < deadline:
    time.sleep(0.2)
check("idle pod stopped by watchdog", STATE["stops"] == 1 and not STATE["running"], str(STATE))
run_id, _ = post_chat("[scenario:basic] ui after stop")
again = read_events(run_id)
check("next request restarts the pod", STATE["starts"] == 2
      and texts(again, "answer") == ["DONE: hello"], str(STATE))

# 9. a pod that never becomes healthy fails the run with a clear message
deadline = time.time() + 10
while STATE["stops"] < 2 and time.time() < deadline:
    time.sleep(0.2)
STATE["warm_polls"], pod_manager.START_TIMEOUT = 10 ** 6, 1.0
run_id, _ = post_chat("[scenario:basic] ui never ready")
failed = texts(read_events(run_id), "answer")[0]
check("start timeout reported in the chat", "Run failed" in failed and "TimeoutError" in failed
      and "GPU pod not healthy" in failed, failed)

# 10. Runpod API key was sent on every call; model endpoint saw no malformed request
check("Runpod calls authenticated", STATE["bad_auth"] == 0 and STATE["starts"] >= 3)
check("no malformed model requests", not mock_llm.ERRORS, "; ".join(mock_llm.ERRORS))

bad = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
web.should_exit = True
sys.exit(1 if bad else 0)
