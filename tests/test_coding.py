from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
TMP = tempfile.TemporaryDirectory(prefix="coding-tests-")
STATE = Path(TMP.name)
WORKSPACE = STATE / "workspace"
WORKSPACE.mkdir()
os.environ.update(AGENT_WORKSPACE=str(WORKSPACE), AGENT_SKILLS=str(ROOT / "skills"),
                  AGENT_TRACE=str(STATE / "trace.jsonl"), AGENT_CHECKPOINTS=str(STATE / "checkpoints"),
                  LLM_API_KEY="EMPTY")
sys.path.insert(0, str(ROOT / "harness"))
import coding
import delivery_tools as dt
import mini_harness as h


class CodingTests(unittest.TestCase):
    def setUp(self):
        self.config = STATE / "checks.json"
        self.config.write_text(json.dumps({"checks": {"tests": {
            "argv": [sys.executable, "-I", "-c",
                     "import runpy; app=runpy.run_path('app.py'); assert app['add'](2,3)==5"],
            "timeout": 10}}, "gate": ["tests"]}), encoding="utf-8")
        coding.configure(str(self.config))
        self.run_id = h.RUN_ID.set(self.id().split(".")[-1])

    def tearDown(self):
        h.RUN_ID.reset(self.run_id)
        dt.close()

    def test_real_tool_loop_builds_delegates_tests_and_reviews(self):
        calls = []

        def model(messages, tools, max_tokens, extras):
            system = messages[0]["content"]
            names = {tool.name for tool in tools}
            calls.append((system, names, h.BUDGET.get()))
            results = [message["content"] for message in messages if message["role"] == "tool"]
            def call(tool_name, **arguments):
                return h.Reply("", [{"id": str(len(calls)), "name": tool_name,
                                     "arguments": json.dumps(arguments)}])
            if system.startswith("You are a worker"):
                self.assertEqual(names, {"read_file", "think"} if "think" in names else {"read_file"})
                return call("read_file", path="app.py") if not results else h.Reply("add is implemented", [])
            if system.startswith("You are an independent reviewer"):
                self.assertLessEqual(names, {"read_file", "list_dir", "think"})
                self.assertIn('"agent": "gate"', messages[1]["content"])
                return call("read_file", path="app.py") if not results else h.Reply("PASS", [])
            self.assertNotIn("run_shell", names)
            self.assertNotIn("git_commit", names)
            self.assertNotIn("git_push_pr", names)
            steps = [("update_plan", {"plan": "[ ] implement\n[ ] test\n[ ] report"}),
                     ("load_skill", {"name": "coding-conventions"}),
                     ("write_file", {"path": "app.py", "content": "def add(a, b):\n    return a + b\n"}),
                     ("spawn_agent", {"task": "Inspect the addition implementation", "tools": ["read_file"]}),
                     ("run_checks", {"name": "tests", "reason": "verify addition"}),
                     ("update_plan", {"plan": "[x] implement\n[x] test\n[ ] report"})]
            if len(results) < len(steps):
                name, arguments = steps[len(results)]
                return call(name, **arguments)
            if any(message["role"] == "user" and message["content"].startswith("Before this goes")
                   for message in messages[2:]):
                return h.Reply("CONFIRMED", [])
            return h.Reply("Implemented integer addition and verified tests.", [])

        with patch.object(h, "call_model", side_effect=model):
            result = coding.run("Implement integer addition with tests")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.checks[0]["exit"], 0)
        self.assertEqual(result.review, "PASS")
        self.assertIn("return a + b", (WORKSPACE / "app.py").read_text())
        self.assertEqual(len({id(budget) for _, _, budget in calls}), 1)
        self.assertIsNone(h.BUDGET.get())
        self.assertEqual(h.TOOL_SCOPE.get(), ())
        self.assertTrue(any(system.startswith("You are a worker") for system, _, _ in calls))

    def test_final_gate_cannot_be_bypassed_by_the_answer(self):
        (WORKSPACE / "app.py").write_text("def add(a, b):\n    return 0\n")
        with patch.object(h, "run_agent", return_value="All tests passed; ship it."), \
                patch.object(h, "review") as reviewer:
            result = coding.run("Implement addition")
        self.assertEqual(result.status, "rejected")
        self.assertNotEqual(result.checks[0]["exit"], 0)
        reviewer.assert_not_called()

    def test_missing_and_timed_out_checks_do_not_accept_a_draft(self):
        for code in (None, -1, 1):
            with self.subTest(code=code), patch.object(h, "run_agent", return_value="Done"), \
                    patch.object(dt, "run_check", return_value=(code, "check unavailable", 0)), \
                    patch.object(h, "review") as reviewer:
                self.assertEqual(coding.run("Build it").status, "rejected")
                reviewer.assert_not_called()

    def test_failed_empty_and_unfinished_reviews_reject(self):
        for verdict in ("FAIL\nMissing behavior", "", "Stopped at the 40-step limit", "PASS but incomplete"):
            with self.subTest(verdict=verdict), patch.object(h, "run_agent", return_value="Done"), \
                    patch.object(dt, "run_check", return_value=(0, "ok", 0)), \
                    patch.object(h, "review", return_value=verdict):
                self.assertEqual(coding.run("Build it").status, "rejected")

    def test_stopped_implementation_never_runs_checks_or_review(self):
        with patch.object(h, "run_agent", return_value="Stopped at the token budget"), \
                patch.object(dt, "run_check") as checks, patch.object(h, "review") as reviewer:
            self.assertEqual(coding.run("Build it").status, "stopped")
            checks.assert_not_called()
            reviewer.assert_not_called()

    def test_shared_deadline_applies_to_final_checks(self):
        with patch.object(h, "run_agent", return_value="Done"), \
                patch.object(dt, "run_check", side_effect=h.BudgetExceeded("time budget")):
            self.assertEqual(coding.run("Build it").status, "stopped")
        self.assertIsNone(h.BUDGET.get())
        self.assertEqual(h.TOOL_SCOPE.get(), ())

    def test_engine_failure_does_not_expose_provider_secrets(self):
        with patch.object(h, "run_agent", side_effect=RuntimeError("secret-provider-value")):
            result = coding.run("Build it")
        self.assertEqual(result.status, "failed")
        self.assertNotIn("secret-provider-value", result.answer)
        self.assertIn("RuntimeError", result.answer)

    def test_no_report_is_not_success(self):
        with patch.object(h, "run_agent", return_value=""), patch.object(dt, "run_check") as checks:
            self.assertEqual(coding.run("Build it").status, "rejected")
            checks.assert_not_called()

    def test_configuration_requires_a_real_gate(self):
        self.config.write_text(json.dumps({"checks": {}, "gate": []}))
        with self.assertRaisesRegex(ValueError, "at least one"):
            coding.configure(str(self.config))
        self.assertIsNone(dt.CONFIG)

    def test_workspace_cannot_own_the_gate_configuration(self):
        with self.assertRaisesRegex(ValueError, "outside the workspace"):
            coding.configure(str(WORKSPACE / "checks.json"))

    def test_disallowed_extra_tools_and_blank_tasks_fail_before_model(self):
        for task, tools in ((" ", ()), ("Build", ("run_shell",)), ("Build", ("git_push_pr",)),
                            ("Build", ("unregistered",))):
            with self.subTest(task=task, tools=tools), patch.object(h, "run_agent") as agent:
                with self.assertRaises(ValueError):
                    coding.run(task, extra_tools=tools)
                agent.assert_not_called()

    def test_budget_bound_sdk_timeout_stops_but_normal_timeout_stays_a_failure(self):
        import httpx
        from openai import APITimeoutError
        for seconds, stopped in ((0.1, True), (900, False), (0, False)):
            with self.subTest(seconds=seconds), patch.object(h, "RUN_MAX_SECONDS", seconds):
                budget = h.RunBudget(h.EFFORTS["high"])
                token = h.BUDGET.set(budget)
                client = Mock()
                client.with_options.return_value.chat.completions.create.side_effect = APITimeoutError(
                    request=httpx.Request("POST", "http://127.0.0.1/model"))
                try:
                    with patch.object(h, "client", client):
                        with self.assertRaises(h.BudgetExceeded if stopped else APITimeoutError):
                            h.call_model([{"role": "system", "content": "test"}, {"role": "user", "content": "task"}], [], 5)
                    self.assertEqual(budget.reserved_tokens, 0)
                    self.assertEqual(budget.stopped, "time budget" if stopped else "")
                finally:
                    h.BUDGET.reset(token)

    def test_check_only_registration_omits_git_tools_even_with_git_config(self):
        config = dt.required()
        with patch.object(dt, "load_config", return_value=type(config)(
                config.source, config.home, config.checks, config.gate, config.stage_gates,
                object(), config.adr_dir, config.adr_required)):
            self.assertEqual(dt.register(str(self.config), checks_only=True), ["run_checks"])
        self.assertNotIn("git_commit", h.REGISTRY)
        self.assertNotIn("git_push_pr", h.REGISTRY)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        h.client.close()
        TMP.cleanup()
