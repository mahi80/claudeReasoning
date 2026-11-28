from __future__ import annotations

import base64
from collections import Counter
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TMP = tempfile.TemporaryDirectory(prefix="integrations-tests-")
STATE = Path(TMP.name)
WORKSPACE = STATE / "workspace"
WORKSPACE.mkdir()
os.environ.update(AGENT_WORKSPACE=str(WORKSPACE), AGENT_TRACE=str(STATE / "trace.jsonl"),
                  AGENT_CHECKPOINTS=str(STATE / "checkpoints"), LLM_API_KEY="EMPTY",
                  TEST_GITHUB_TOKEN="test-github-secret", TEST_GITLAB_TOKEN="test-gitlab-secret",
                  TEST_JIRA_TOKEN="test-jira-secret", TEST_JIRA_USER="test@example.invalid")
sys.path.insert(0, str(ROOT / "harness"))
import httpx
import integrations as i
import mini_harness as h

SHA = "a" * 40


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = None
        self.config = STATE / "integrations.json"
        self.spec = {"services": {service: {
            "url": f"https://{service}.example" + ("/api/v4" if service == "gitlab" else "/rest/api/3" if service == "jira" else ""),
            "token_env": f"TEST_{service.upper()}_TOKEN", "tools": sorted(i.SUPPORTED[service]),
            "resources": ["team/repo" if service == "github" else "group/repo" if service == "gitlab" else "PROJ"]}
            for service in i.SUPPORTED}}
        self.load()

    def load(self):
        i.close()
        self.config.write_text(json.dumps(self.spec), encoding="utf-8")
        self.names = i.load_config(str(self.config))
        for connector in i.CLIENTS:
            headers = dict(connector.client.headers)
            connector.client.close()
            connector.client = httpx.Client(transport=httpx.MockTransport(self.handle), headers=headers,
                                            follow_redirects=False, trust_env=False)

    def handle(self, request):
        self.requests.append(request)
        if self.response:
            return self.response(request)
        path = request.url.path
        if request.method == "GET" and "/git/ref/" in path:
            data = {"object": {"sha": SHA}}
        elif request.method == "GET" and "/git/commits/" in path:
            data = {"tree": {"sha": "b" * 40}}
        elif request.method == "POST" and path.endswith("/git/trees"):
            data = {"sha": "c" * 40}
        elif request.method == "POST" and path.endswith("/git/commits"):
            data = {"sha": "d" * 40}
        elif request.method == "GET" and "/repository/branches/" in path:
            data = {"commit": {"id": SHA}}
        elif request.method == "GET" and ("/contents/" in path or "/repository/files/" in path):
            data = {"content": base64.b64encode(b"print('hello')\n").decode(), "encoding": "base64", "last_commit_id": SHA}
        else:
            data = {"ok": True}
        return httpx.Response(200, json=data)

    def tearDown(self):
        i.close()

    def arguments(self, service, operation):
        values = {"resource": self.spec["services"][service]["resources"][0], "path": "src/app.py", "ref": "main", "page": 2,
                  "cursor": "next-page", "issue": "PROJ-12" if service == "jira" else "12", "number": 12,
                  "branch": "feature/task", "source": "main", "target": "main", "expected_head": SHA,
                  "message": "Implement task", "files": [{"path": "src/app.py", "content": "print('hello')\n"}],
                  "title": "Implement feature", "body": "Description", "verdict": "REQUEST_CHANGES", "transition": "31"}
        return {key: values[key] for key in i.fields_for(service, operation)}

    def execute(self, service, operation, arguments=None):
        name = f"{service}__{operation}"
        return h.execute({"name": name, "arguments": json.dumps(arguments or self.arguments(service, operation))},
                         {name: h.REGISTRY[name]}, Counter())

    def test_all_supported_provider_operations_dispatch(self):
        with patch.object(h, "ask_operator", return_value=True):
            for service, operations in i.SUPPORTED.items():
                for operation in sorted(operations):
                    with self.subTest(service=service, operation=operation):
                        before = len(self.requests)
                        result = self.execute(service, operation)
                        self.assertFalse(result.startswith("ERROR"), result)
                        self.assertGreater(len(self.requests), before)

    def test_reads_do_not_request_approval(self):
        with patch.object(h, "ask_operator") as ask:
            for service in i.SUPPORTED:
                self.assertFalse(self.execute(service, "list_issues").startswith("ERROR"))
            ask.assert_not_called()

    def test_every_write_denied_before_http_even_with_auto_approve(self):
        with patch.object(h, "ask_operator", return_value=False) as ask, patch.object(h, "AUTO_APPROVE", True):
            for service, operations in i.SUPPORTED.items():
                for operation in operations - i.READS:
                    self.assertTrue(self.execute(service, operation).startswith("DENIED"))
            self.assertGreater(ask.call_count, 0)
        self.assertEqual(self.requests, [])

    def test_unattended_writes_fail_closed(self):
        with patch.object(h, "ask_operator", h.no_operator), patch.object(h, "AUTO_APPROVE", True):
            self.assertTrue(self.execute("github", "create_issue").startswith("DENIED"))
        self.assertEqual(self.requests, [])

    def test_authentication_stays_on_configured_provider(self):
        for service in i.SUPPORTED:
            self.execute(service, "list_issues")
            request = self.requests[-1]
            self.assertEqual(request.url.host, f"{service}.example")
            if service == "gitlab":
                self.assertEqual(request.headers["PRIVATE-TOKEN"], "test-gitlab-secret")
                self.assertNotIn("Authorization", request.headers)
            else:
                self.assertEqual(request.headers["Authorization"], f"Bearer test-{service}-secret")

    def test_jira_cloud_basic_auth_uses_environment_only(self):
        self.spec["services"]["jira"]["user_env"] = "TEST_JIRA_USER"
        self.load()
        self.execute("jira", "get_issue")
        encoded = self.requests[-1].headers["Authorization"].split(" ", 1)[1]
        self.assertEqual(base64.b64decode(encoded).decode(), "test@example.invalid:test-jira-secret")
        self.assertNotIn("test-jira-secret", json.dumps(h.REGISTRY["jira__get_issue"].schema()))

    def test_cross_resource_and_cross_project_issue_access_rejected(self):
        for service in i.SUPPORTED:
            arguments = self.arguments(service, "get_issue")
            arguments["resource"] = "OTHER" if service == "jira" else "other/repo"
            self.assertTrue(self.execute(service, "get_issue", arguments).startswith("ERROR"))
        arguments = self.arguments("jira", "get_issue") | {"issue": "OTHER-12"}
        self.assertTrue(self.execute("jira", "get_issue", arguments).startswith("ERROR"))
        self.assertEqual(self.requests, [])

    def test_paths_and_refs_cannot_rewrite_endpoint(self):
        for path in ("../secret", "/outside", "a/../b", "a%2F..%2Fsecret", "a\\b", "a?ref=other", "a//b"):
            for service in ("github", "gitlab"):
                arguments = self.arguments(service, "read_file") | {"path": path}
                self.assertTrue(self.execute(service, "read_file", arguments).startswith("ERROR"))
        for ref in ("../main", "main?other", "main\n", "a//b", "a@{b", "a.lock"):
            arguments = self.arguments("github", "read_file") | {"ref": ref}
            self.assertTrue(self.execute("github", "read_file", arguments).startswith("ERROR"))
        self.assertEqual(self.requests, [])

    def test_bad_types_unknown_fields_and_operation_injection_rejected(self):
        for extra in ({"page": True}, {"page": 0}, {"url": "https://outside.example"},
                      {"operation": "create_issue"}, {"client": "other"}):
            self.assertTrue(self.execute("github", "list_issues",
                                        self.arguments("github", "list_issues") | extra).startswith("ERROR"))
        self.assertEqual(self.requests, [])

    def test_config_requires_explicit_tools_resources_and_external_credentials(self):
        cases = ({"tools": []}, {"tools": ["run_shell"]}, {"resources": []},
                 {"resources": ["../repo"]}, {"token_env": "MISSING_TEST_CREDENTIAL"},
                 {"token": "not-allowed"}, {"url": "http://public.example"},
                 {"url": "https://user:password@provider.example"}, {"url": "https://provider.example?token=secret"})
        original = dict(self.spec["services"]["github"])
        for change in cases:
            with self.subTest(change=change):
                i.close()
                self.spec["services"]["github"] = original | change
                self.config.write_text(json.dumps(self.spec))
                with self.assertRaises((ValueError, TypeError)):
                    i.load_config(str(self.config))
                self.assertFalse(i.REGISTERED)
                self.assertFalse(i.CLIENTS)
        with self.assertRaisesRegex(ValueError, "outside"):
            i.load_config(str(WORKSPACE / "config.json"))

    def test_redirect_does_not_send_credentials_elsewhere(self):
        self.response = lambda request: httpx.Response(302, headers={"Location": "https://outside.example/steal"})
        self.assertIn("HTTP 302", self.execute("github", "list_issues"))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.host, "github.example")

    def test_provider_errors_do_not_expose_response_secrets(self):
        self.response = lambda request: httpx.Response(403, text="secret body test-github-secret")
        result = self.execute("github", "list_issues")
        self.assertIn("HTTP 403", result)
        self.assertNotIn("secret body", result)
        self.assertNotIn("test-github-secret", result)

    def test_uncertain_writes_report_unknown_outcome_without_retry(self):
        def timeout(request):
            raise httpx.ReadTimeout("private provider body", request=request)
        self.response = timeout
        with patch.object(h, "ask_operator", return_value=True):
            result = self.execute("github", "create_request")
        self.assertIn("unknown", result)
        self.assertNotIn("private provider body", result)
        self.assertEqual(len(self.requests), 1)

    def test_returned_credentials_are_redacted(self):
        self.response = lambda request: httpx.Response(200, json={"echo": "Bearer test-github-secret"})
        self.assertNotIn("test-github-secret", self.execute("github", "list_issues"))

    def test_repository_files_are_decoded_as_text(self):
        for service in ("github", "gitlab"):
            result = json.loads(self.execute(service, "read_file"))
            self.assertEqual(result["content"], "print('hello')\n")
            self.assertEqual(result["encoding"], "utf-8")

    def test_pagination_is_passed_to_each_provider(self):
        for service in ("github", "gitlab"):
            self.execute(service, "request_diff")
            self.assertEqual(self.requests[-1].url.params["page"], "2")
            self.assertEqual(self.requests[-1].url.params["per_page"], "20")
        self.execute("jira", "list_issues")
        params = self.requests[-1].url.params
        self.assertEqual(params["nextPageToken"], "next-page")
        self.assertEqual(params["jql"], 'project = "PROJ" ORDER BY created DESC')

    def test_merges_and_reviews_pin_the_expected_commit(self):
        with patch.object(h, "ask_operator", return_value=True):
            for service in ("github", "gitlab"):
                self.execute(service, "merge_request")
                self.assertEqual(json.loads(self.requests[-1].content)["sha"], SHA)
            self.execute("github", "review_request")
            self.assertEqual(json.loads(self.requests[-1].content)["commit_id"], SHA)
            self.execute("gitlab", "approve_request")
            self.assertEqual(json.loads(self.requests[-1].content)["sha"], SHA)

    def test_github_commit_never_force_pushes(self):
        with patch.object(h, "ask_operator", return_value=True):
            result = self.execute("github", "commit_files")
        self.assertFalse(result.startswith("ERROR"), result)
        self.assertEqual(self.requests[-1].method, "PATCH")
        self.assertFalse(json.loads(self.requests[-1].content)["force"])
        commit = next(r for r in self.requests if r.method == "POST" and r.url.path.endswith("/git/commits"))
        self.assertEqual(json.loads(commit.content)["parents"], [SHA])

    def test_stale_branch_head_cannot_publish(self):
        with patch.object(h, "ask_operator", return_value=True):
            for service in ("github", "gitlab"):
                args = self.arguments(service, "commit_files") | {"expected_head": "f" * 40}
                self.assertIn("head changed", self.execute(service, "commit_files", args))
        self.assertTrue(all(request.method == "GET" for request in self.requests))

    def test_gitlab_commit_uses_per_file_concurrency_guard(self):
        with patch.object(h, "ask_operator", return_value=True):
            self.execute("gitlab", "commit_files")
        action = json.loads(self.requests[-1].content)["actions"][0]
        self.assertEqual(action["action"], "update")
        self.assertEqual(action["last_commit_id"], SHA)
        self.assertNotIn("force", json.loads(self.requests[-1].content))

    def test_jira_mutations_use_adf_and_explicit_transition(self):
        with patch.object(h, "ask_operator", return_value=True):
            self.execute("jira", "create_issue")
            fields = json.loads(self.requests[-1].content)["fields"]
            self.assertEqual(fields["project"], {"key": "PROJ"})
            self.assertEqual(fields["description"]["type"], "doc")
            self.execute("jira", "transition_issue")
            self.assertEqual(json.loads(self.requests[-1].content), {"transition": {"id": "31"}})

    def test_duplicate_registration_is_rejected_without_removing_existing_tools(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            i.load_config(str(self.config))
        self.assertEqual(set(self.names), i.REGISTERED)

    def test_scope_and_worker_grants_remain_explicit(self):
        name = "github__list_issues"
        result = h.execute({"name": name, "arguments": json.dumps(self.arguments("github", "list_issues"))}, {}, Counter())
        self.assertIn("unknown tool", result)
        self.assertEqual(self.requests, [])
        self.assertEqual(h.REGISTRY[name].parameters["properties"]["resource"]["enum"], ["team/repo"])

    def test_shared_budget_deadline_still_stops_network_calls(self):
        with patch.object(h, "time_left", side_effect=h.BudgetExceeded("time budget")):
            with self.assertRaises(h.BudgetExceeded):
                i.CLIENTS[0].call("list_issues", **self.arguments("github", "list_issues"))
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        i.close()
        h.client.close()
        TMP.cleanup()
