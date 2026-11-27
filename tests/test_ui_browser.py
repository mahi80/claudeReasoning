"""Real-browser test of the HTMX chat UI (headless Chrome through Playwright).

Skips cleanly when Playwright or Chrome is missing. Run: python tests/test_ui_browser.py
Writes screenshots to docs/ when SCREENSHOT_DIR is set.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("harness", "tests", "app"):
    sys.path.insert(0, str(ROOT / folder))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP browser test: playwright is not installed")
    sys.exit(0)
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
if not CHROME:
    print("SKIP browser test: no Chrome or Chromium found")
    sys.exit(0)

import mock_llm  # noqa: E402
import mock_runpod  # noqa: E402

llm_server, llm_port = mock_llm.start()
rp_server, rp_port = mock_runpod.start()
tmp = Path(tempfile.mkdtemp(prefix="harness-ui-"))
os.environ.update(
    LLM_BASE_URL=f"http://127.0.0.1:{llm_port}/v1", LLM_API_KEY="test-key", LLM_MODEL="mock",
    AGENT_WORKSPACE=str(tmp / "workspace"), AGENT_SKILLS=str(tmp / "skills"),
    AGENT_TRACE=str(tmp / "trace.jsonl"), AGENT_CHECKPOINTS=str(tmp / "checkpoints"),
    RUNPOD_API=f"http://127.0.0.1:{rp_port}/v1", RUNPOD_POD_ID="pod123",
    RUNPOD_API_KEY="rp-key", LLM_HEALTH_URL=f"http://127.0.0.1:{rp_port}/health",
    POD_POLL_SECONDS="0.5", POD_IDLE_SECONDS="600", POD_START_TIMEOUT="30",
    APPROVAL_TIMEOUT="30")
mock_runpod.STATE["warm_polls"] = 4        # about two seconds of visible "starting GPU"

import uvicorn  # noqa: E402

import server  # noqa: E402

server.h.WORKSPACE.mkdir(parents=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
web = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
threading.Thread(target=web.run, daemon=True).start()
while not web.started:
    time.sleep(0.05)

shots = os.environ.get("SCREENSHOT_DIR")
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 420, "height": 760}, device_scale_factor=2)
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.goto(f"http://127.0.0.1:{port}/")

    # first task: the pod is stopped, so the chat should show the GPU start
    page.fill("input[name=message]", "Save a note that says hello, then read it back")
    page.click("form button")
    first = page.locator(".msg.agent").nth(0)
    first.locator(".status", has_text="Starting the GPU pod").wait_for(timeout=10000)
    check("browser shows GPU start status", True)
    if shots:
        page.screenshot(path=f"{shots}/ui-starting-gpu.png")
    first.locator(".answer", has_text="DONE: hello").wait_for(timeout=30000)
    check("browser shows the answer", first.locator(".answer").inner_text() == "DONE: hello")
    check("status line cleared at the end", first.locator(".status").inner_text().strip() == "")
    check("form reset after sending", page.input_value("input[name=message]") == "")

    # second task: needs approval twice; deny the first, approve the second
    page.fill("input[name=message]", "Delete the old build folder")
    page.click("form button")
    second = page.locator(".msg.agent").nth(1)
    second.get_by_role("button", name="Deny").wait_for(timeout=15000)
    if shots:
        page.screenshot(path=f"{shots}/ui-approval.png")
    asked = second.locator(".approval").inner_text()
    check("approval prompt names the command", "rm -rf important" in asked, asked)
    second.get_by_role("button", name="Deny").click()
    second.locator(".approval code", has_text="ls; rm -rf important").wait_for(timeout=15000)
    second.get_by_role("button", name="Approve").click()
    second.locator(".answer", has_text="exit=0").wait_for(timeout=30000)
    answer = second.locator(".answer").inner_text()
    check("denied and approved commands reflected in the answer",
          answer.startswith("DENIED") and answer.count("exit=") == 2, answer)
    check("approval area cleared", second.locator(".approval button").count() == 0)
    check("two user bubbles and two agent bubbles",
          page.locator(".msg.user").count() == 2 and page.locator(".msg.agent").count() == 2)

    # third task: a longer job, so the agent's checklist shows up and gets ticked off
    page.fill("input[name=message]", "Write the weekly report")
    page.click("form button")
    third = page.locator(".msg.agent").nth(2)
    third.locator(".answer", has_text="plan seen").wait_for(timeout=30000)
    plan = third.locator(".plan").inner_text()
    check("plan checklist shown and ticked off in the chat",
          "[x] write the file" in plan and "[ ] report back" in plan, plan)
    if shots:
        third.screenshot(path=f"{shots}/ui-plan.png")
    check("no JavaScript errors", not errors, "; ".join(errors))
    if shots:
        page.screenshot(path=f"{shots}/ui-done.png", full_page=True)
    browser.close()

bad = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} browser checks passed")
web.should_exit = True
sys.exit(1 if bad else 0)
