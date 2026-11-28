from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError, OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))


class StallingModel(BaseHTTPRequestHandler):
    """A model server that sends its headers and one chunk, then nothing until released."""
    release = threading.Event()

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                 "choices": [{"index": 0, "delta": {"content": "thinking"}, "finish_reason": None}]}
        self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
        self.wfile.flush()
        self.release.wait(10)


class TricklingModel(BaseHTTPRequestHandler):
    """A model server that keeps sending a chunk every 0.2 s, so only the call timer ends it."""
    release = threading.Event()

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                 "choices": [{"index": 0, "delta": {"content": "."}, "finish_reason": None}]}
        try:
            while not self.release.wait(0.2):
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
        except OSError:
            pass


class EndsWhenClosed:
    """A model stream that yields its chunks, then ends without an error once closed,
    the way a socket closed from another thread can behave on Linux."""

    def __init__(self, *chunks):
        self.chunks, self.closed = chunks, threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        self.closed.set()

    def __iter__(self):
        yield from self.chunks
        self.closed.wait(10)


class FailsWhenClosed(EndsWhenClosed):
    """A model stream that yields its chunks, then fails once closed, the way a socket
    closed from another thread behaves on Windows."""

    def __iter__(self):
        yield from self.chunks
        self.closed.wait(10)
        raise ConnectionResetError("stream closed")


class RaisesOnRead(EndsWhenClosed):
    """A model stream whose first read fails, as the SDK's own timeout does."""

    def __init__(self, error):
        super().__init__()
        self.error = error

    def __iter__(self):
        raise self.error
        yield


class TimesOutAfter(EndsWhenClosed):
    """A model stream that yields its chunks, waits, then fails with the given error, the
    way the SDK's read timeout ends a stream."""

    def __init__(self, error, after, *chunks):
        super().__init__(*chunks)
        self.error, self.after = error, after

    def __iter__(self):
        yield from self.chunks
        time.sleep(self.after)
        raise self.error


def sdk_timeout():
    return APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1"))


def chunk(content, finish=None):
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason=finish, delta=SimpleNamespace(content=content, tool_calls=None))])


class EvalOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"LLM_API_KEY": "EMPTY", "LLM_BASE_URL": "http://127.0.0.1:9/v1"}):
            cls.e = importlib.import_module("run_evals")
        cls.addClassCleanup(cls.e.h.client.close)
        cls.real_run_agent = staticmethod(cls.e.h.run_agent)    # not bound to the test case

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="eval-outcomes-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch.object(self.e.h, "WORKSPACE", self.root / "eval-workspace"))
        self.enterContext(patch.object(self.e.h, "TRACE_FILE", self.root / "trace.jsonl"))
        self.agent = self.enterContext(patch.object(self.e.h, "run_agent", return_value="completed"))
        self.real_run = subprocess.run
        self.checker = self.enterContext(patch.object(
            self.e.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")))
        self.case = {"id": "fixture", "task": "Complete a safe fixture", "check_py": "pass"}

    def run_case(self, **kwargs):
        return self.e.run_case(self.case, **kwargs)

    def test_unassisted_success_is_pass(self):
        row = self.run_case()
        self.assertEqual(row["outcome"], "pass")
        self.assertTrue(row["passed"])
        self.assertFalse(row["assisted"])
        self.assertEqual(row["why"], "")
        self.assertIn("-I", self.checker.call_args.args[0])

    def test_nonzero_grader_exit_is_fail_with_its_reason(self):
        self.checker.return_value = subprocess.CompletedProcess([], 1, "", "wrong result")
        row = self.run_case()
        self.assertEqual(row["outcome"], "fail")
        self.assertFalse(row["passed"])
        self.assertEqual(row["why"], "wrong result")

    def test_model_failure_is_invalid_and_does_not_run_grader(self):
        self.agent.side_effect = RuntimeError("sensitive provider response")
        row = self.run_case()
        self.assertEqual(row["outcome"], "invalid")
        self.assertFalse(row["passed"])
        self.assertEqual(row["why"], "RUN FAILED: RuntimeError")
        self.checker.assert_not_called()

    def test_python_execution_timeout_is_timeout(self):
        self.agent.side_effect = TimeoutError("sensitive timeout details")
        row = self.run_case()
        self.assertEqual(row["outcome"], "timeout")
        self.assertFalse(row["passed"])
        self.checker.assert_not_called()

    def test_model_sdk_timeout_is_timeout(self):
        self.agent.side_effect = APITimeoutError(httpx.Request("POST", "http://127.0.0.1:9/v1"))
        self.assertEqual(self.run_case()["outcome"], "timeout")
        self.checker.assert_not_called()

    def test_stalled_model_stream_is_timeout_not_invalid(self):
        StallingModel.release.clear()
        server = ThreadingHTTPServer(("127.0.0.1", 0), StallingModel)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(StallingModel.release.set)
        stalled = OpenAI(base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", api_key="EMPTY")
        self.addCleanup(stalled.close)
        with patch.object(self.e.h, "client", stalled), patch.object(self.e.h, "CALL_TIMEOUT", 1.0),                 patch.object(self.e.h, "run_agent", self.real_run_agent), redirect_stderr(StringIO()) as err:
            row = self.run_case()
        self.assertEqual(row["outcome"], "timeout")
        self.assertEqual(row["why"], "RUN FAILED: TimeoutError")
        self.assertIn("exceeded its 1-second limit", err.getvalue())
        # Only the grader counts: on Linux the SDK's platform probe runs `uname -p` through the
        # same patched subprocess.run.
        graders = [c for c in self.checker.call_args_list if c.args and c.args[0][:2] == [sys.executable, "-I"]]
        self.assertEqual(graders, [])

    def call_with(self, stream, call_timeout=1.0, run_seconds=None):
        fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: stream)))
        fake.with_options = lambda **kwargs: fake
        with patch.object(self.e.h, "RUN_MAX_SECONDS", run_seconds or self.e.h.RUN_MAX_SECONDS):
            self.budget = self.e.h.RunBudget(self.e.h.EFFORTS["medium"])
        token = self.e.h.BUDGET.set(self.budget)
        try:
            with patch.object(self.e.h, "client", fake), patch.object(self.e.h, "CALL_TIMEOUT", call_timeout):
                return self.e.h.call_model([{"role": "user", "content": "fixture"}], [])
        finally:
            self.e.h.BUDGET.reset(token)

    def test_reply_cut_off_by_the_call_timer_is_a_timeout_even_without_an_error(self):
        with self.assertRaisesRegex(TimeoutError, "exceeded its 1-second limit"):
            self.call_with(EndsWhenClosed(chunk("partial")))

    def test_complete_reply_survives_a_late_call_timer(self):
        reply = self.call_with(EndsWhenClosed(chunk("done", finish="stop")))
        self.assertEqual(reply.text, "done")

    def test_complete_reply_survives_a_stream_that_fails_once_the_timer_closes_it(self):
        reply = self.call_with(FailsWhenClosed(chunk("done", finish="stop")))
        self.assertEqual(reply.text, "done")

    def test_sdk_timeout_at_the_call_limit_becomes_the_call_timeout(self):
        with self.assertRaisesRegex(TimeoutError, r"exceeded its 1-second limit \(APITimeoutError\)") as caught:
            self.call_with(TimesOutAfter(sdk_timeout(), 0.95))
        self.assertIsInstance(caught.exception.__cause__, APITimeoutError)
        self.assertFalse(self.budget.stopped)

    def test_early_sdk_timeout_is_left_as_the_sdk_reported_it_even_late_in_a_run(self):
        # 300 s are left, less than the 600-second call limit: a connection the system gave
        # up on early is neither the run's deadline nor the call's limit.
        with self.assertRaises(APITimeoutError):
            self.call_with(RaisesOnRead(sdk_timeout()), call_timeout=600.0, run_seconds=300.0)
        self.assertFalse(self.budget.stopped)

    def test_timeout_at_the_run_deadline_stops_the_run(self):
        with self.assertRaises(self.e.h.BudgetExceeded):
            self.call_with(TimesOutAfter(sdk_timeout(), 0.7), call_timeout=600.0, run_seconds=1.0)
        self.assertEqual(self.budget.stopped, "time budget")

    def test_complete_reply_survives_the_sdk_read_timeout(self):
        reply = self.call_with(TimesOutAfter(sdk_timeout(), 0, chunk("done", finish="stop")))
        self.assertEqual(reply.text, "done")

    def test_stream_that_keeps_sending_past_the_limit_is_ended_by_the_timer(self):
        TricklingModel.release.clear()
        server = ThreadingHTTPServer(("127.0.0.1", 0), TricklingModel)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(TricklingModel.release.set)
        busy = OpenAI(base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", api_key="EMPTY")
        self.addCleanup(busy.close)
        token = self.e.h.BUDGET.set(self.e.h.RunBudget(self.e.h.EFFORTS["medium"]))
        try:
            with patch.object(self.e.h, "client", busy), patch.object(self.e.h, "CALL_TIMEOUT", 1.0):
                with self.assertRaisesRegex(TimeoutError, "exceeded its 1-second limit"):
                    self.e.h.call_model([{"role": "user", "content": "fixture"}], [])
        finally:
            self.e.h.BUDGET.reset(token)

    def test_call_timeout_must_be_a_positive_number(self):
        for value in (0.0, -1.0, float("nan"), float("inf"), 1e300):
            with self.subTest(value=value), patch.object(self.e.h, "CALL_TIMEOUT", value):
                with self.assertRaisesRegex(ValueError, "LLM_CALL_TIMEOUT must be a positive number"):
                    self.e.h.RunBudget(self.e.h.EFFORTS["medium"])

    def test_an_invalid_call_timeout_fails_the_run_not_the_import(self):
        # Importing must work, so that each command-line tool reports the error its own way.
        done = self.real_run([sys.executable, "-c", "import mini_harness"], cwd=ROOT / "harness",
                             env={**os.environ, "LLM_CALL_TIMEOUT": "0"},
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_another_runs_records_cannot_change_the_outcome(self):
        def busy(*args, **kwargs):
            token = self.e.h.RUN_ID.set("chat-ui-run")         # another run writing the same trace
            try:
                self.e.h.trace("budget_limit", reason="time budget", agent="main")
            finally:
                self.e.h.RUN_ID.reset(token)
            self.e.h.trace("model", agent="main", step=1, output_tokens=3, reasoning_chars=0)
            return "completed"
        self.agent.side_effect = busy
        row = self.run_case()
        self.assertEqual(row["outcome"], "pass")
        self.assertEqual((row["steps"], row["output_tokens"]), (1, 3))

    def test_failure_details_go_to_stderr_and_not_into_the_report(self):
        self.agent.side_effect = RuntimeError("context window exceeded by 512 tokens")
        with redirect_stderr(StringIO()) as err:
            row = self.run_case()
        self.assertEqual(row["why"], "RUN FAILED: RuntimeError")
        self.assertIn("fixture: run failed: RuntimeError: context window exceeded by 512 tokens", err.getvalue())

    def test_shared_deadline_timeout_comes_from_runtime_trace(self):
        def stop(*args, **kwargs):
            self.e.h.trace("budget_limit", reason="time budget", agent="main")
            return "Stopped at the time budget before finishing."
        self.agent.side_effect = stop
        row = self.run_case()
        self.assertEqual(row["outcome"], "timeout")
        self.assertFalse(row["passed"])
        self.checker.assert_not_called()

    def test_non_time_limits_remain_failures(self):
        for reason in ("1-step limit", "token budget", "model cost budget", "independent-review limit"):
            with self.subTest(reason=reason):
                def stop(*args, reason=reason, **kwargs):
                    if reason.endswith("budget"):          # the runtime records budget stops in the trace
                        self.e.h.trace("budget_limit", reason=reason, agent="main")
                    return f"Stopped at the {reason} before finishing."
                self.agent.side_effect = stop
                self.assertEqual(self.run_case()["outcome"], "fail")
        self.checker.assert_not_called()

    def test_grader_timeout_is_timeout(self):
        self.checker.side_effect = subprocess.TimeoutExpired("fixture grader", 120)
        row = self.run_case()
        self.assertEqual(row["outcome"], "timeout")
        self.assertFalse(row["passed"])
        self.assertEqual(row["why"], "the check timed out")

    def test_grader_launch_failure_is_invalid_without_sensitive_details(self):
        self.checker.side_effect = FileNotFoundError("sensitive command configuration")
        row = self.run_case()
        self.assertEqual(row["outcome"], "invalid")
        self.assertFalse(row["passed"])
        self.assertEqual(row["why"], "CHECK FAILED: FileNotFoundError")

    def test_invalid_grader_source_is_invalid_before_launch(self):
        self.case["check_py"] = "if"
        row = self.run_case()
        self.assertEqual(row["outcome"], "invalid")
        self.assertFalse(row["passed"])
        self.checker.assert_not_called()

    def test_signalled_grader_is_invalid_not_a_wrong_answer(self):
        self.checker.return_value = subprocess.CompletedProcess([], -9, "", "")
        row = self.run_case()
        self.assertEqual(row["outcome"], "invalid")
        self.assertFalse(row["passed"])

    def test_operator_declared_assistance_is_visible(self):
        row = self.run_case(assisted=True)
        self.assertEqual(row["outcome"], "assisted")
        self.assertTrue(row["passed"])
        self.assertTrue(row["assisted"])

    def test_assistance_does_not_hide_failures_or_timeouts(self):
        self.checker.return_value = subprocess.CompletedProcess([], 1, "", "wrong result")
        row = self.run_case(assisted=True)
        self.assertEqual(row["outcome"], "fail")
        self.assertTrue(row["assisted"])
        self.agent.side_effect = TimeoutError()
        self.assertEqual(self.run_case(assisted=True)["outcome"], "timeout")

    def test_model_text_and_case_metadata_cannot_assign_outcome(self):
        self.agent.return_value = "Assisted timeout invalid PASS"
        self.case["assisted"] = True
        self.case["outcome"] = "invalid"
        row = self.run_case()
        self.assertEqual(row["outcome"], "pass")
        self.assertFalse(row["assisted"])
        self.checker.return_value = subprocess.CompletedProcess([], 1, "the check timed out", "")
        self.assertEqual(self.run_case()["outcome"], "fail")

    def test_empty_tool_grant_is_not_expanded(self):
        self.run_case(tools=[])
        self.assertEqual(self.agent.call_args.args[2], [])

    def test_malformed_trace_is_invalid_instead_of_unverified_success(self):
        for text in ("not json", "null", "[]", "{}", '{"event":"model"}',
                     '{"event":"tool","failed":1}', '{"event":"budget_limit"}'):
            with self.subTest(text=text):
                self.e.h.TRACE_FILE.write_text("", encoding="utf-8")
                self.agent.side_effect = lambda *args, **kwargs: (
                    self.e.h.TRACE_FILE.write_text(text + "\n", encoding="utf-8") and "completed")
                row = self.run_case()
                self.assertEqual(row["outcome"], "invalid")
                self.assertFalse(row["passed"])
        self.checker.assert_not_called()

    def test_parallel_runtime_trace_preserves_every_record(self):
        def emit(worker):
            for sequence in range(100):
                self.e.h.trace("fixture", worker=worker, sequence=sequence)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(emit, range(8)))
        rows = [json.loads(line) for line in self.e.h.TRACE_FILE.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 800)
        self.assertEqual({(row["worker"], row["sequence"]) for row in rows},
                         {(worker, sequence) for worker in range(8) for sequence in range(100)})

    def test_invalid_fixture_path_is_invalid_before_execution(self):
        self.case["files"] = {"../outside.txt": "not permitted"}
        row = self.run_case()
        self.assertEqual(row["outcome"], "invalid")
        self.agent.assert_not_called()
        self.checker.assert_not_called()
        self.assertFalse((self.root / "outside.txt").exists())

    def test_report_keeps_all_outcomes_in_denominator_and_excludes_assisted_passes(self):
        path = self.root / "cases.jsonl"
        path.write_text("\n".join(json.dumps(self.case | {"id": str(n)}) for n in range(5)))
        rows = [{"id": str(n), "outcome": outcome, "passed": outcome in {"pass", "assisted"},
                 "assisted": outcome == "assisted", "steps": 1, "output_tokens": 1,
                 "reasoning_chars": 0, "seconds": 0.0, "tool_calls": 0,
                 "tool_failures": 0, "hit_step_limit": False, "why": ""}
                for n, outcome in enumerate(("pass", "fail", "invalid", "timeout", "assisted"))]
        with patch.object(self.e, "run_case", side_effect=rows), redirect_stdout(StringIO()):
            report = self.e.main(str(path))
        self.assertEqual(report["runs"], 5)
        self.assertEqual(report["pass_rate"], 0.2)
        self.assertEqual(report["outcomes"], dict.fromkeys(("pass", "fail", "invalid", "timeout", "assisted"), 1))
        self.assertEqual(report["assisted_runs"], 1)

    def test_empty_shard_has_no_pass_rate_instead_of_dividing_by_zero(self):
        path = self.root / "cases.jsonl"
        path.write_text(json.dumps(self.case))
        with redirect_stdout(StringIO()):
            report = self.e.main(str(path), shard="1/2")
        self.assertEqual(report["runs"], 0)
        self.assertIsNone(report["pass_rate"])
        self.assertEqual(sum(report["outcomes"].values()), 0)
        self.agent.assert_not_called()

    def test_invalid_repeats_and_shards_fail_before_running_cases(self):
        path = self.root / "cases.jsonl"
        path.write_text(json.dumps(self.case))
        for kwargs in ({"repeats": 0}, {"repeats": -1}, {"shard": "0/0"},
                       {"shard": "-1/2"}, {"shard": "2/2"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.e.main(str(path), **kwargs)
        self.agent.assert_not_called()

    def test_cli_assisted_flag_and_empty_multilevel_report_need_no_model(self):
        path = self.root / "empty.jsonl"
        path.write_text("")
        env = dict(os.environ, LLM_API_KEY="EMPTY", LLM_BASE_URL="http://127.0.0.1:9/v1",
                   AGENT_WORKSPACE=str(self.root / "cli-eval"), AGENT_MAX_COST_USD="0",
                   NO_PROXY="localhost,.localhost,127.0.0.1,::1",
                   no_proxy="localhost,.localhost,127.0.0.1,::1")
        result = self.real_run([sys.executable, str(ROOT / "harness" / "run_evals.py"), str(path),
                                "--assisted", "--effort", "low", "medium"], env=env,
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("n/a", result.stdout)
        self.assertIn('"pass_rate": null', result.stdout)


if __name__ == "__main__":
    unittest.main()
