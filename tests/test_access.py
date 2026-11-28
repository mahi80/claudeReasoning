from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import threading
import time
import unittest
from unittest.mock import patch

import httpx
import uvicorn
from coding_ui_fixture import Fixture
import mock_llm

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    PORT = sock.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
FIXTURE = Fixture(BASE)
s = FIXTURE.server
from access import Access, Principal

WEB = uvicorn.Server(uvicorn.Config(s.app, host="127.0.0.1", port=PORT, log_level="error"))
THREAD = threading.Thread(target=WEB.run, daemon=True)
THREAD.start()
DEADLINE = time.monotonic() + 10
while not WEB.started and time.monotonic() < DEADLINE:
    time.sleep(0.01)
assert WEB.started, "fixture did not start"


class AccessConfigTests(unittest.TestCase):
    def setUp(self):
        self.access = Access()
        self.config = json.loads(FIXTURE.auth_config.read_text())
        self.path = FIXTURE.state / "unit-access.json"

    def configure(self, config=None):
        self.path.write_text(json.dumps(self.config if config is None else config))
        self.access.configure(str(self.path), FIXTURE.workspace)

    def test_external_config_is_required(self):
        with self.assertRaises(ValueError):
            self.access.configure("", FIXTURE.workspace)
        inside = FIXTURE.workspace / "access.json"
        inside.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            self.access.configure(str(inside), FIXTURE.workspace)

    def test_exact_single_tenant_configuration(self):
        for config in ([], {}, {**self.config, "tenants": {}}, {**self.config, "tenant": "../team"},
                       {**self.config, "tenant": True}, {**self.config, "users": {}},
                       {**self.config, "users": {"../alice": {"token_env": "FIXTURE_CHAT_ALICE"}}},
                       {**self.config, "users": {"alice": {"token": FIXTURE.token}}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.configure(config)

    def test_origin_requires_https_or_loopback_without_credentials_or_path(self):
        for origin in (None, "http://chat.example.test", "https://user:secret@chat.example.test",
                       "https://chat.example.test/", "https://chat.example.test?x=1", "https://chat.example.test#x",
                       "file:///chat", "http://127.0.0.1:bad", "https://chat.example.test/path"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.configure({**self.config, "origin": origin})
        for origin in ("https://chat.example.test", "http://[::1]:8080", BASE):
            self.configure({**self.config, "origin": origin})
            self.assertEqual(self.access.origin, origin)

    def test_credentials_are_external_distinct_and_strong(self):
        for token in ("", "short", "a" * 513, "a" * 31 + " ", "a" * 31 + "\n", "a" * 31 + "é"):
            with self.subTest(token=token), patch.dict(os.environ, FIXTURE_CHAT_ALICE=token), self.assertRaises(ValueError):
                self.configure()
        with patch.dict(os.environ, FIXTURE_CHAT_BOB=FIXTURE.token), self.assertRaises(ValueError):
            self.configure()
        for env in ("MISSING_CHAT_TOKEN_123", "INVALID-NAME", True):
            with self.subTest(env=env), self.assertRaises(ValueError):
                self.configure({**self.config, "users": {"alice": {"token_env": env}}})

    def test_session_lifetime_is_bounded(self):
        for seconds in (0, 59, 86401, True, "3600"):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                self.configure({**self.config, "session_seconds": seconds})
        self.configure({**self.config, "session_seconds": 120})
        self.assertEqual(self.access.session_seconds, 120)

    def test_tokens_are_hashed_and_resolve_to_configured_identity(self):
        self.configure()
        principal, key, browser = self.access.authenticate("Bearer " + FIXTURE.token, None)
        self.assertEqual(principal, Principal("fixture-team", "alice"))
        self.assertFalse(browser)
        self.assertEqual(len(key), 32)
        self.assertNotIn(FIXTURE.token, repr(self.access.__dict__))
        self.assertNotIn(FIXTURE.other_token, repr(self.access.__dict__))

    def test_invalid_authorization_cannot_fall_back_to_valid_cookie(self):
        self.configure()
        cookie = self.access.login(FIXTURE.token)
        for header in ("", "Basic " + FIXTURE.token, "Bearer wrong", "Bearer  " + FIXTURE.token,
                       "Bearer " + FIXTURE.other_token + " extra", "Bearer " + "x" * 513):
            self.assertIsNone(self.access.authenticate(header, cookie))
        self.assertTrue(self.access.authenticate(None, cookie)[2])
        self.assertIsNone(self.access.authenticate(None, "made-up-session-" + "x" * 32))
        self.assertIsNone(self.access.login("x" * 32))

    def test_sessions_expire_and_are_removed(self):
        self.configure()
        with patch("access.time.monotonic", return_value=100):
            cookie = self.access.login(FIXTURE.token)
        with patch("access.time.monotonic", return_value=3700):
            self.assertIsNone(self.access.authenticate(None, cookie))
        self.assertFalse(self.access.sessions)

    def test_sessions_are_bounded_per_user_not_daily_task_quotas(self):
        self.configure()
        cookies = [self.access.login(FIXTURE.token) for _ in range(12)]
        bob = self.access.login(FIXTURE.other_token)
        self.assertEqual(len(self.access.sessions), 9)
        self.assertIsNone(self.access.authenticate(None, cookies[0]))
        self.assertIsNotNone(self.access.authenticate(None, cookies[-1]))
        self.access.logout(cookies[-1])
        self.assertIsNotNone(self.access.authenticate(None, bob))

    def test_failed_reconfiguration_preserves_existing_authentication(self):
        self.configure()
        with self.assertRaises(ValueError):
            self.configure({})
        self.assertIsNotNone(self.access.authenticate("Bearer " + FIXTURE.token, None))
        self.access.close()
        self.assertFalse(self.access.origin)
        self.assertIsNone(self.access.authenticate("Bearer " + FIXTURE.token, None))


class AccessHTTPTests(unittest.TestCase):
    def setUp(self):
        self.alice = httpx.Client(base_url=BASE, headers=FIXTURE.headers, timeout=40)
        self.bob = httpx.Client(base_url=BASE, headers={"Authorization": "Bearer " + FIXTURE.other_token}, timeout=40)
        self.browser = httpx.Client(base_url=BASE, timeout=40)

    def tearDown(self):
        self.alice.close()
        self.bob.close()
        self.browser.close()

    def sign_in(self, client=None, token=None):
        client = self.browser if client is None else client
        response = client.post("/login", data={"token": FIXTURE.token if token is None else token}, headers={"Origin": BASE})
        self.assertEqual(response.status_code, 303, response.text)
        return client.cookies.get(Access.cookie)

    def completed_run(self, client=None):
        client = self.alice if client is None else client
        with patch.object(s.coding, "run", return_value=s.coding.Result("accepted", "owned fixture result")):
            response = client.post("/chat", data={"message": "ownership fixture", "mode": "coding", "owner": "bob", "tenant": "other"},
                                   headers={"Origin": BASE})
            self.assertEqual(response.status_code, 200, response.text)
            run_id = re.search(r'sse-connect="/runs/(\w+)/events"', response.text).group(1)
            with s.RUNS[run_id].changed:
                self.assertTrue(s.RUNS[run_id].changed.wait_for(lambda: s.RUNS[run_id].finished, timeout=5))
        return run_id

    def test_unauthenticated_routes_fail_before_model_or_tool_execution(self):
        before, runs = len(mock_llm.REQUESTS), len(s.RUNS)
        for method, path in (("POST", "/chat"), ("GET", "/runs/nope/events"), ("POST", "/runs/nope/approval/nope/allow"),
                             ("GET", "/docs"), ("GET", "/openapi.json"), ("POST", "/logout")):
            response = self.browser.request(method, path, data={"message": "x"})
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(before, len(mock_llm.REQUESTS))
        self.assertEqual(runs, len(s.RUNS))
        page = self.browser.get("/", headers={"Accept": "text/html"})
        self.assertEqual(page.status_code, 303)
        self.assertEqual(page.headers["location"], "/login")
        self.assertEqual(self.browser.get("/login").status_code, 200)
        self.assertEqual(self.browser.get("/static/htmx.min.js").status_code, 200)

    def test_query_credentials_and_spoofed_proxy_headers_do_not_authenticate(self):
        response = self.browser.get("/", params={"token": FIXTURE.token},
                                    headers={"X-Forwarded-User": "alice", "X-Forwarded-For": "127.0.0.1"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.alice.get("/", headers={"Host": "untrusted.example.test"}).status_code, 400)

    def test_login_requires_same_origin_and_never_echoes_credentials(self):
        for origin in (None, "null", "https://other.example.test"):
            headers = {"Origin": origin} if origin else {}
            response = self.browser.post("/login", data={"token": FIXTURE.token}, headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(FIXTURE.token, response.text)
        invalid = "invalid-private-token-" + "x" * 32
        response = self.browser.post("/login", data={"token": invalid}, headers={"Origin": BASE})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid access token", response.text)
        self.assertNotIn(invalid, response.text)
        self.assertNotIn(Access.cookie, self.browser.cookies)

    def test_login_cookie_is_opaque_http_only_strict_and_allows_chat(self):
        cookie = self.sign_in()
        self.assertNotIn(FIXTURE.token, cookie)
        response = self.browser.post("/login", data={"token": FIXTURE.token}, headers={"Origin": BASE})
        header = response.headers["set-cookie"]
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=strict", header)
        self.assertIn("Max-Age=3600", header)
        self.assertNotIn("Domain=", header)
        self.assertEqual(self.browser.get("/").status_code, 200)
        run = self.completed_run(self.browser)
        self.assertEqual(s.RUNS[run].owner, Principal("fixture-team", "alice"))
        self.assertIn("owned fixture result", self.browser.get(f"/runs/{run}/events").text)

    def test_https_sessions_require_secure_cookies(self):
        async def check():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app), base_url="https://chat.example.test") as client:
                response = await client.post("/login", data={"token": FIXTURE.token}, headers={"Origin": "https://chat.example.test"})
                self.assertEqual(response.status_code, 303)
                self.assertIn("Secure", response.headers["set-cookie"])
        with patch.object(s.ACCESS, "origin", "https://chat.example.test"):
            asyncio.run(check())

    def test_logout_revokes_only_that_session_and_cannot_be_replayed(self):
        cookie = self.sign_in()
        response = self.browser.post("/logout", headers={"Origin": BASE})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.browser.get("/").status_code, 401)
        self.browser.cookies.set(Access.cookie, cookie)
        self.assertEqual(self.browser.get("/").status_code, 401)
        self.assertEqual(self.alice.get("/").status_code, 200)
        self.assertEqual(self.bob.get("/").status_code, 200)

    def test_cookie_mutations_reject_cross_origin_or_missing_origin(self):
        self.sign_in()
        before = len(s.RUNS)
        for origin in (None, "null", "https://other.example.test"):
            headers = {"Origin": origin} if origin else {}
            for path in ("/chat", "/logout", "/runs/nope/approval/nope/allow"):
                self.assertEqual(self.browser.post(path, data={"message": "x"}, headers=headers).status_code, 403)
        self.assertEqual(before, len(s.RUNS))
        self.assertEqual(self.browser.get("/").status_code, 200)

    def test_run_owner_comes_from_authentication_and_foreign_runs_look_missing(self):
        run = self.completed_run()
        self.assertEqual(s.RUNS[run].owner, Principal("fixture-team", "alice"))
        self.assertIn("owned fixture result", self.alice.get(f"/runs/{run}/events").text)
        foreign = self.bob.get(f"/runs/{run}/events")
        unknown = self.bob.get("/runs/missing/events")
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.text, unknown.text)
        other_tenant = s.Run(Principal("other-team", "alice"))
        other_tenant.emit("answer", "other tenant private", last=True)
        s.RUNS[other_tenant.id] = other_tenant
        self.assertEqual(self.alice.get(f"/runs/{other_tenant.id}/events").status_code, 404)

    def test_foreign_user_cannot_approve_a_known_pending_prompt(self):
        run = s.Run(Principal("fixture-team", "alice"))
        s.RUNS[run.id] = run
        decisions = []
        worker = threading.Thread(target=lambda: decisions.append(run.ask("github__create_request", {"resource": "team/repo"})))
        worker.start()
        try:
            with run.changed:
                self.assertTrue(run.changed.wait_for(lambda: any("hx-post" in text for _, text in run.events), timeout=5))
                approval = run.pending_approval
            target = f"/runs/{run.id}/approval/{approval}/allow"
            with patch.object(s.h, "AUTO_APPROVE", True):
                self.assertEqual(self.bob.post(target).status_code, 404)
            self.assertFalse(run.answered.is_set())
            self.assertEqual(run.pending_approval, approval)
            self.assertEqual(self.alice.post(target).text, "Approved")
            worker.join(5)
            self.assertEqual(decisions, [True])
            self.assertEqual(self.alice.post(target).status_code, 409)
        finally:
            run.answered.set()
            worker.join(5)
            run.emit("done", "ok", last=True)

    def test_expired_session_cannot_submit_or_read_runs(self):
        cookie = self.sign_in()
        run = self.completed_run()
        with s.ACCESS.lock:
            key = s.ACCESS.digest(cookie)
            owner, _ = s.ACCESS.sessions[key]
            s.ACCESS.sessions[key] = (owner, 0)
        self.assertEqual(self.browser.get(f"/runs/{run}/events").status_code, 401)
        self.assertEqual(self.browser.post("/chat", data={"message": "x"}, headers={"Origin": BASE}).status_code, 401)

    def test_open_event_stream_rechecks_revoked_sessions_before_more_data(self):
        cookie = self.sign_in()
        run = s.Run(Principal("fixture-team", "alice"))
        s.RUNS[run.id] = run
        run.emit("status", "initial event")
        received, ready = [], threading.Event()
        def read():
            with self.browser.stream("GET", f"/runs/{run.id}/events") as response:
                for line in response.iter_lines():
                    received.append(line)
                    if line == "data: initial event":
                        ready.set()
        reader = threading.Thread(target=read)
        reader.start()
        try:
            self.assertTrue(ready.wait(5))
            s.ACCESS.logout(cookie)
            run.emit("answer", "private after logout", last=True)
            reader.join(5)
            self.assertFalse(reader.is_alive())
            self.assertNotIn("data: private after logout", received)
            self.assertTrue(any("Session expired" in line for line in received))
            self.assertIn("event: done", received)
        finally:
            run.emit("done", "ok", last=True)
            reader.join(5)

    def test_real_coding_does_not_send_access_credentials_to_model_or_trace(self):
        response = self.alice.post("/chat", data={"message": "[scenario:coding] authenticated addition", "mode": "coding", "effort": "high"})
        self.assertEqual(response.status_code, 200, response.text)
        run = re.search(r'sse-connect="/runs/(\w+)/events"', response.text).group(1)
        result = self.alice.get(f"/runs/{run}/events").text
        self.assertIn("Accepted", result)
        self.assertIn("Independent review:<br>PASS", result)
        self.assertIn("tests: passed", result)
        evidence = json.dumps(mock_llm.REQUESTS) + FIXTURE.server.h.TRACE_FILE.read_text() + result
        self.assertNotIn(FIXTURE.token, evidence)
        self.assertNotIn(FIXTURE.other_token, evidence)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        WEB.should_exit = True
        THREAD.join(10)
        FIXTURE.close()
