"""Real-browser test of the HTMX chat UI (headless Chrome through Playwright).

Skips cleanly when Playwright or Chrome is missing. Run: python tests/test_ui_browser.py
Writes screenshots to docs/ when SCREENSHOT_DIR is set.
"""
from __future__ import annotations

import json
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
CHROME = (shutil.which("google-chrome") or shutil.which("chromium")
          or shutil.which("chromium-browser") or shutil.which("chrome"))
if not CHROME and sys.platform == "win32":
    candidates = [Path(root) / "Google/Chrome/Application/chrome.exe"
                  for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
                  if (root := os.environ.get(name))]
    CHROME = next((str(path) for path in candidates if path.is_file()), None)
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
    APPROVAL_TIMEOUT="30", AGENT_CHAT_AUTH_CONFIG=str(tmp / "access.json"),
    FIXTURE_CHAT_TOKEN="local-browser-fixture-" + "a" * 32)
mock_runpod.STATE["warm_polls"] = 4        # about two seconds of visible "starting GPU"
config = tmp / "mcp.json"
config.write_text(json.dumps({"servers": {"demo": {
    "command": sys.executable, "args": [str(ROOT / "tests" / "demo_mcp_server.py")],
    "tools": ["add"]}}}), encoding="utf-8")
os.environ["AGENT_MCP_CONFIG"] = str(config)
skill = tmp / "skills" / "arithmetic"
skill.mkdir(parents=True)
(skill / "SKILL.md").write_text(
    "---\nname: arithmetic\ndescription: Add integers using the arithmetic MCP tool.\n---\n"
    "Use demo__add and report its actual result.\n", encoding="utf-8")

import uvicorn  # noqa: E402

import server  # noqa: E402

server.h.WORKSPACE.mkdir(parents=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
(tmp / "access.json").write_text(json.dumps({"tenant": "fixture-team", "origin": f"http://127.0.0.1:{port}",
    "users": {"fixture": {"token_env": "FIXTURE_CHAT_TOKEN"}}}))
web = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error"))
web_thread = threading.Thread(target=web.run, daemon=True)
web_thread.start()
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
    check("browser requires sign-in", page.url.endswith("/login"))
    page.fill("input[name=token]", os.environ["FIXTURE_CHAT_TOKEN"])
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.locator("input[name=message]").wait_for(timeout=10000)
    check("browser login reaches chat", True)

    # first task: the pod is stopped, so the chat should show the GPU start
    page.fill("input[name=message]", "Save a note that says hello, then read it back")
    page.click('form[hx-post="/chat"] button')
    first = page.locator(".msg.agent").nth(0)
    first.locator(".status", has_text="Starting the GPU pod").wait_for(timeout=10000)
    check("browser shows GPU start status", True)
    if shots:
        page.screenshot(path=f"{shots}/ui-starting-gpu.png")
    first.locator(".answer", has_text="DONE: hello").wait_for(timeout=30000)
    check("browser shows the answer", first.locator(".answer").inner_text() == "DONE: hello")
    check("status line cleared at the end", first.locator(".status").inner_text().strip() == "")
    bubble = first.bounding_box()
    composer = page.locator('form[hx-post="/chat"]').bounding_box()
    check("composer does not obscure the reply", bubble["y"] + bubble["height"] <= composer["y"])
    check("form reset after sending", page.input_value("input[name=message]") == "")

    # second task: needs approval twice; deny the first, approve the second
    page.fill("input[name=message]", "Delete the old build folder")
    page.click('form[hx-post="/chat"] button')
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

    # third task: a longer job at high effort, so the checklist shows up and gets ticked
    page.select_option("select[name=effort]", "high")
    page.fill("input[name=message]", "Write the weekly report")
    page.click('form[hx-post="/chat"] button')
    third = page.locator(".msg.agent").nth(2)
    third.locator(".answer", has_text="plan seen").wait_for(timeout=30000)
    levels = [e["effort"] for e in map(json.loads, server.h.TRACE_FILE.read_text().splitlines())
              if e["event"] == "run"]
    check("effort picked in the browser reaches the harness, and the picker keeps it",
          levels == ["medium", "medium", "high"]
          and page.input_value("select[name=effort]") == "high"
          and page.input_value("input[name=message]") == "", str(levels))
    plan = third.locator(".plan").inner_text()
    check("plan checklist shown and ticked off in the chat",
          "[x] write the file" in plan and "[ ] report back" in plan, plan)
    if shots:
        third.screenshot(path=f"{shots}/ui-plan.png")
    page.select_option("select[name=effort]", "medium")
    page.fill("input[name=message]", "[scenario:parallel_approvals] two workers need permission")
    page.click('form[hx-post="/chat"] button')
    fourth = page.locator(".msg.agent").nth(3)
    fourth.get_by_role("button", name="Approve").wait_for(timeout=15000)
    first_id = fourth.locator(".approval-request").get_attribute("id")
    check("concurrent workers show one approval at a time",
          fourth.get_by_role("button", name="Approve").count() == 1
          and fourth.get_by_role("button", name="Deny").count() == 1)

    def delayed_approval(route) -> None:
        response = route.fetch()
        page.wait_for_function(
            "oldId => { const p = document.querySelector('.msg.agent:last-child .approval-request'); "
            "return p && p.id !== oldId; }", arg=first_id, timeout=15000)
        route.fulfill(response=response)

    page.route("**/runs/*/approval/*/allow", delayed_approval)
    with page.expect_response("**/runs/*/approval/*/allow") as permission_response:
        fourth.get_by_role("button", name="Approve").click()
    permission_response.value.finished()
    fourth.get_by_role("button", name="Deny").wait_for(timeout=15000)
    check("late approval response does not replace the next prompt",
          fourth.locator(".approval-request").get_attribute("id") != first_id
          and fourth.get_by_role("button", name="Approve").count() == 1)
    page.unroute("**/runs/*/approval/*/allow", delayed_approval)
    fourth.get_by_role("button", name="Deny").click()
    fourth.locator(".answer", has_text="REPORTS:").wait_for(timeout=30000)
    answer = fourth.locator(".answer").inner_text()
    check("parallel worker approvals produce separate results",
          answer.count("exit=0") == 1 and answer.count("DENIED") == 1, answer)
    check("concurrent approval area is cleared at completion",
          fourth.locator(".approval button").count() == 0)
    page.select_option("select[name=effort]", "xhigh")
    page.fill("input[name=message]", "[scenario:review] repair and review the answer")
    page.click('form[hx-post="/chat"] button')
    fifth = page.locator(".msg.agent").nth(4)
    fifth.locator(".answer", has_text="answer two").wait_for(timeout=30000)
    check("browser shows the repaired answer after it passes review",
          fifth.locator(".answer").inner_text() == "answer two"
          and (server.h.WORKSPACE / "r.txt").read_text() == "right")
    page.fill("input[name=message]", "[scenario:review] stubborn agent")
    page.click('form[hx-post="/chat"] button')
    sixth = page.locator(".msg.agent").nth(5)
    sixth.locator(".answer", has_text="Stopped at the independent-review limit").wait_for(timeout=30000)
    check("browser reports review failure instead of accepting the draft",
          sixth.locator(".answer").inner_text().startswith("Stopped at the independent-review limit")
          and sixth.locator(".status").inner_text().strip() == ""
          and sixth.locator(".approval button").count() == 0)
    page.select_option("select[name=effort]", "medium")
    page.fill("input[name=message]", "[scenario:basic] continue after a rejected answer")
    page.click('form[hx-post="/chat"] button')
    seventh = page.locator(".msg.agent").nth(6)
    seventh.locator(".answer", has_text="DONE: hello").wait_for(timeout=30000)
    check("chat remains usable after a review fails",
          seventh.locator(".answer").inner_text() == "DONE: hello"
          and page.input_value("input[name=message]") == "")
    page.fill("input[name=message]", "[scenario:workflow] use a skill and MCP worker")
    page.click('form[hx-post="/chat"] button')
    eighth = page.locator(".msg.agent").nth(7)
    eighth.get_by_role("button", name="Approve").wait_for(timeout=15000)
    check("a scoped worker's configured MCP call asks for approval in chat",
          "demo__add" in eighth.locator(".approval").inner_text())
    eighth.get_by_role("button", name="Approve").click()
    eighth.locator(".answer", has_text="DONE: sum=5").wait_for(timeout=30000)
    check("chat completes planning, skill loading, delegation and MCP execution",
          eighth.locator(".answer").inner_text() == "DONE: sum=5"
          and "[x] write report" in eighth.locator(".plan").inner_text()
          and (server.h.WORKSPACE / "report.txt").read_text() == "sum=5")
    previous_tokens = server.h.RUN_MAX_TOKENS
    server.h.RUN_MAX_TOKENS = 1
    try:
        page.fill("input[name=message]", "[scenario:basic] exceed the token budget")
        page.click('form[hx-post="/chat"] button')
        ninth = page.locator(".msg.agent").nth(8)
        ninth.locator(".answer", has_text="Stopped at the token budget").wait_for(timeout=30000)
        check("chat reports shared budget exhaustion instead of a successful answer",
              ninth.locator(".answer").inner_text().startswith("Stopped at the token budget")
              and ninth.locator(".approval button").count() == 0)
    finally:
        server.h.RUN_MAX_TOKENS = previous_tokens
    page.fill("input[name=message]", "[scenario:basic] recover after the budget stop")
    page.click('form[hx-post="/chat"] button')
    tenth = page.locator(".msg.agent").nth(9)
    tenth.locator(".answer", has_text="DONE: hello").wait_for(timeout=30000)
    check("a new chat task gets its own execution budget",
          tenth.locator(".answer").inner_text() == "DONE: hello")
    check("no JavaScript errors", not errors, "; ".join(errors))
    if shots:
        page.screenshot(path=f"{shots}/ui-done.png", full_page=True)
    browser.close()

bad = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(bad)}/{len(results)} browser checks passed")
web.should_exit = True
web_thread.join(timeout=10)
sys.exit(1 if bad else 0)
