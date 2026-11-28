from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import mock_integrations
import mock_llm

LLM, PORT = mock_llm.start()
PROVIDER, PROVIDER_PORT = mock_integrations.start()


class CodeCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code-cli-tests-")
        self.state = Path(self.temp.name)
        self.workspace = self.state / "workspace"
        self.workspace.mkdir()
        self.config = self.state / "checks.json"
        self.config.write_text(json.dumps({"checks": {"tests": {"argv": [sys.executable, "-I", "-c",
            "import runpy; m=runpy.run_path('app.py'); assert m['add'](2, 3)==5"], "timeout": 10}}, "gate": ["tests"]}))
        self.integrations = self.state / "integrations.json"
        self.integrations.write_text(json.dumps(mock_integrations.configuration(PROVIDER_PORT)))
        self.result = self.state / "result.json"
        self.env = {**os.environ, "LLM_BASE_URL": f"http://127.0.0.1:{PORT}/v1", "LLM_API_KEY": "test-key",
                    "LLM_MODEL": "mock", "AGENT_WORKSPACE": str(self.workspace), "AGENT_SKILLS": str(ROOT / "skills"),
                    "AGENT_TRACE": str(self.state / "trace.jsonl"), "AGENT_CHECKPOINTS": str(self.state / "checkpoints"),
                    "AGENT_DELIVERY_CONFIG": str(self.config), "AGENT_MCP_CONFIG": "", "AGENT_INTEGRATIONS_CONFIG": "",
                    "RUNPOD_POD_ID": "", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
                    "FIXTURE_CONNECTOR_TOKEN": "fixture-token", "AGENT_AUTO_APPROVE": "0"}

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, stdin=None, env=None):
        return subprocess.run([sys.executable, str(ROOT / "harness" / "code_cli.py"), *args],
                              cwd=ROOT, env=env or self.env, input=stdin, capture_output=True, text=True, timeout=60)

    def test_one_shot_runs_real_tools_gates_review_and_structured_result(self):
        process = self.run_cli("--run-id", "cli-test", "--result", str(self.result), "[scenario:coding] implement addition")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads(self.result.read_text())
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["checks"][0]["exit"], 0)
        self.assertEqual(result["review"], "PASS")
        self.assertEqual(result["run"], "cli-test")
        self.assertIn("return a + b", (self.workspace / "app.py").read_text())
        self.assertIn("Coding: review", process.stderr)
        events = [json.loads(line) for line in (self.state / "trace.jsonl").read_text().splitlines()]
        self.assertTrue(any(event.get("agent") == "worker" for event in events))

    def test_gate_failure_has_nonzero_exit_and_rejected_result(self):
        process = self.run_cli("--result", str(self.result), "[scenario:coding] badgate")
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        result = json.loads(self.result.read_text())
        self.assertEqual(result["status"], "rejected")
        self.assertNotEqual(result["checks"][0]["exit"], 0)
        self.assertEqual(result["review"], "")

    def test_review_failure_cannot_exit_successfully(self):
        process = self.run_cli("--result", str(self.result), "[scenario:coding] reviewfail")
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        self.assertEqual(json.loads(self.result.read_text())["status"], "rejected")

    def test_execution_stop_has_distinct_exit_code(self):
        process = self.run_cli("--result", str(self.result), "[scenario:coding] stopped",
                               env=self.env | {"AGENT_MAX_TOTAL_TOKENS": "1"})
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(json.loads(self.result.read_text())["status"], "stopped")

    def test_interactive_tasks_get_separate_runs(self):
        process = self.run_cli("--interactive", stdin="[scenario:coding] first\n[scenario:coding] second\n/exit\n")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(process.stdout.count("ACCEPTED ["), 2)
        events = [json.loads(line) for line in (self.state / "trace.jsonl").read_text().splitlines()]
        self.assertEqual(len({event["run"] for event in events if event["event"] == "coding_stage"}), 2)

    def test_bad_inputs_do_not_call_model(self):
        cases = [("--run-id", "../outside", "task"), ("--resume", "task"),
                 ("--interactive", "--run-id", "shared"), ("--result", str(self.workspace / "result.json"), "task"),
                 ("--effort", "turbo", "task")]
        before = len(mock_llm.REQUESTS)
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual(len(mock_llm.REQUESTS), before)

    def test_missing_or_workspace_owned_config_fails_closed(self):
        before = len(mock_llm.REQUESTS)
        process = self.run_cli("task", env=self.env | {"AGENT_DELIVERY_CONFIG": ""})
        self.assertEqual(process.returncode, 2)
        process = self.run_cli("--config", str(self.workspace / "checks.json"), "task")
        self.assertEqual(process.returncode, 3)
        self.assertEqual(len(mock_llm.REQUESTS), before)

    def test_one_shot_connectors_read_all_providers_and_deny_publication(self):
        before = len(mock_integrations.CALLS)
        process = self.run_cli("[scenario:coding] connectors", env=self.env | {
            "AGENT_INTEGRATIONS_CONFIG": str(self.integrations), "AGENT_AUTO_APPROVE": "1"})
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        calls = mock_integrations.CALLS[before:]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call["method"] == "GET" and call["authenticated"] for call in calls))
        self.assertTrue(any(call["path"].startswith("/jira/search/jql") for call in calls))

    def test_interactive_connector_publication_requires_explicit_yes(self):
        for choice, expected in (("no", 0), ("yes", 1)):
            with self.subTest(choice=choice):
                before = len(mock_integrations.CALLS)
                process = self.run_cli("--interactive", stdin=f"[scenario:coding] connectors {choice}\n{choice}\n/exit\n",
                                       env=self.env | {"AGENT_INTEGRATIONS_CONFIG": str(self.integrations)})
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                writes = [call for call in mock_integrations.CALLS[before:] if call["method"] != "GET"]
                self.assertEqual(len(writes), expected)
                self.assertIn("github__create_request", process.stderr)

    def test_provider_keys_are_not_in_model_requests_or_output(self):
        before = len(mock_llm.REQUESTS)
        process = self.run_cli("[scenario:coding] connectors secrecy", env=self.env | {
            "AGENT_INTEGRATIONS_CONFIG": str(self.integrations)})
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertNotIn("fixture-token", json.dumps(mock_llm.REQUESTS[before:]))
        self.assertNotIn("test-key", process.stdout + process.stderr)
        self.assertNotIn("fixture-token", process.stdout + process.stderr)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        LLM.shutdown()
        PROVIDER.shutdown()
