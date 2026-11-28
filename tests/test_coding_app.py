from __future__ import annotations

import json
import re
import socket
import threading
import time
import unittest
from unittest.mock import patch

import httpx
import uvicorn
from coding_ui_fixture import Fixture
import mock_integrations

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    PORT = sock.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
FIXTURE = Fixture(BASE)
s = FIXTURE.server
HTTP = httpx.Client(headers=FIXTURE.headers)
WEB = uvicorn.Server(uvicorn.Config(s.app, host="127.0.0.1", port=PORT, log_level="error"))
THREAD = threading.Thread(target=WEB.run, daemon=True)
THREAD.start()
DEADLINE = time.monotonic() + 10
while not WEB.started and time.monotonic() < DEADLINE:
    time.sleep(0.01)
assert WEB.started, "fixture did not start"


def post(message: str, mode: str = "coding"):
    response = HTTP.post(BASE + "/chat", data={"message": message, "effort": "high", "mode": mode}, timeout=10)
    assert response.status_code == 200, response.text
    return re.search(r'sse-connect="/runs/(\w+)/events"', response.text).group(1), response.text


def events(run_id: str, callback=None):
    rows = []
    with HTTP.stream("GET", BASE + f"/runs/{run_id}/events", timeout=40) as response:
        kind, lines = "", []
        for line in response.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                lines.append(line[6:])
            elif line == "" and kind:
                text = "\n".join(lines)
                rows.append((kind, text))
                if callback:
                    callback(kind, text)
                if kind == "done":
                    break
                kind, lines = "", []
    return rows


def answer(rows):
    return next(text for kind, text in rows if kind == "answer")


class CodingAppTests(unittest.TestCase):
    def test_configured_page_defaults_to_coding_and_high_effort(self):
        page = HTTP.get(BASE + "/").text
        self.assertIn('name="mode" value="coding" checked', page)
        self.assertIn('value="high" selected', page)
        self.assertIn('aria-label="Task"', page)

    def test_http_coding_uses_real_executor_and_reports_verified_result(self):
        run, _ = post("[scenario:coding] HTTP addition")
        rows = events(run)
        text = answer(rows)
        self.assertTrue(text.startswith("Accepted"), text)
        self.assertIn("tests: passed", text)
        self.assertIn("Independent review:<br>PASS", text)
        self.assertIn("return a + b", (FIXTURE.workspace / "app.py").read_text())
        self.assertIn(("status", "Coding: checks"), rows)
        self.assertIn(("status", "Coding review: passed"), rows)
        self.assertEqual(rows[-1], ("done", "ok"))
        self.assertEqual(events(run), rows)

    def test_failing_gate_is_rejected_not_accepted(self):
        run, _ = post("[scenario:coding] HTTP badgate")
        text = answer(events(run))
        self.assertTrue(text.startswith("Rejected"), text)
        self.assertIn("tests: did not pass", text)
        self.assertNotIn("Independent review:<br>PASS", text)

    def test_failed_review_is_rejected(self):
        run, _ = post("[scenario:coding] HTTP reviewfail")
        text = answer(events(run))
        self.assertTrue(text.startswith("Rejected"), text)
        self.assertIn("Missing requested behavior", text)

    def test_stopped_budget_is_not_accepted(self):
        with patch.object(s.h, "RUN_MAX_TOKENS", 1):
            run, _ = post("[scenario:coding] HTTP stopped")
            rows = events(run)
        self.assertTrue(answer(rows).startswith("Stopped"))
        self.assertIn(("status", "Execution stopped: token budget"), rows)

    def test_general_mode_still_works(self):
        run, _ = post("[scenario:basic] HTTP general", "chat")
        text = answer(events(run))
        self.assertIn("DONE: hello", text)
        self.assertNotIn("Accepted", text)

    def test_invalid_modes_blank_tasks_and_unconfigured_coding_rejected(self):
        for data in ({"message": "x", "mode": "invalid"}, {"message": "   ", "mode": "coding"}):
            self.assertEqual(HTTP.post(BASE + "/chat", data=data).status_code, 422)
        with patch.object(s, "CODING_CONFIG", ""):
            self.assertEqual(HTTP.post(BASE + "/chat", data={"message": "x", "mode": "coding"}).status_code, 503)
            page = HTTP.get(BASE + "/").text
            self.assertIn('value="coding" disabled', page)
            self.assertIn('value="medium" selected', page)

    def test_user_report_and_review_text_are_escaped(self):
        run, fragment = post("[scenario:coding] HTTP xss <script>alert(1)</script>")
        text = answer(events(run))
        self.assertNotIn("<script>", fragment + text)
        self.assertIn("&lt;script&gt;", fragment)
        self.assertIn("&lt;script&gt;", text)

    def test_coding_failures_do_not_expose_provider_exception_text(self):
        with patch.object(s.coding, "run", side_effect=RuntimeError("private-provider-secret")):
            run, _ = post("[scenario:coding] HTTP exception")
            text = answer(events(run))
        self.assertIn("RuntimeError", text)
        self.assertNotIn("private-provider-secret", text)

    def test_general_tasks_cannot_modify_workspace_during_coding_gate(self):
        started, release, general = threading.Event(), threading.Event(), threading.Event()
        def coding_work(*args, **kwargs):
            started.set()
            assert release.wait(10)
            return s.coding.Result("accepted", "fixture")
        def general_work(*args, **kwargs):
            general.set()
            return "general fixture"
        with patch.object(s.coding, "run", side_effect=coding_work), patch.object(s.h, "run_agent", side_effect=general_work):
            first, _ = post("coding lock fixture")
            try:
                self.assertTrue(started.wait(5))
                second, _ = post("general lock fixture", "chat")
                queued = s.RUNS[second]
                with queued.changed:
                    self.assertTrue(queued.changed.wait_for(lambda: ("status", "Waiting for the shared workspace") in queued.events, timeout=5))
                self.assertFalse(general.is_set())
            finally:
                release.set()
            events(first)
            events(second)
            self.assertTrue(general.is_set())
            self.assertFalse(s.WORKSPACE_LOCK.locked())

    def test_connectors_reads_are_automatic_and_each_publication_has_approval(self):
        for choice, expected in (("deny", 0), ("allow", 1)):
            with self.subTest(choice=choice):
                before = len(mock_integrations.CALLS)
                decisions = []
                def decide(kind, text):
                    if kind == "approval" and "hx-post" in text:
                        self.assertIn("github__create_request", text)
                        target = re.search(r'hx-post="([^"]+/' + choice + ')"', text).group(1)
                        decisions.append(HTTP.post(BASE + target).text)
                with patch.object(s.h, "AUTO_APPROVE", True):
                    run, _ = post(f"[scenario:coding] HTTP connectors {choice}")
                    rows = events(run, decide)
                self.assertTrue(answer(rows).startswith("Accepted"), answer(rows))
                self.assertEqual(decisions, ["Approved" if expected else "Denied"])
                calls = mock_integrations.CALLS[before:]
                self.assertEqual(sum(call["method"] == "GET" for call in calls), 3)
                self.assertEqual(sum(call["method"] != "GET" for call in calls), expected)
                self.assertTrue(all(call["authenticated"] for call in calls))

    def test_result_and_trace_do_not_contain_connector_credentials(self):
        lines = (FIXTURE.state / "trace.jsonl").read_text()
        self.assertNotIn("fixture-token", lines)
        self.assertNotIn("test-key", lines)
        self.assertNotIn("fixture-token", json.dumps(s.EXTRA_TOOLS))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        WEB.should_exit = True
        THREAD.join(10)
        FIXTURE.close()
