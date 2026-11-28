from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))


class CheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"LLM_API_KEY": "EMPTY", "LLM_BASE_URL": "http://127.0.0.1:9/v1",
                                     "AGENT_MAX_COST_USD": "0"}):
            cls.h = importlib.import_module("mini_harness")
        cls.addClassCleanup(cls.h.client.close)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="checkpoint-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in (("CHECKPOINT_DIR", self.root / "checkpoints"),
                            ("WORKSPACE", self.root / "workspace"),
                            ("TRACE_FILE", self.root / "trace.jsonl")):
            self.enterContext(patch.object(self.h, name, value))
        self.h.WORKSPACE.mkdir()
        self.enterContext(patch.object(self.h, "call_model", side_effect=AssertionError("No live model")))
        self.budget = self.h.RunBudget(self.h.EFFORTS["medium"])
        token = self.h.BUDGET.set(self.budget)
        run = self.h.RUN_ID.set("checkpoint-fixture")
        self.addCleanup(self.h.BUDGET.reset, token)
        self.addCleanup(self.h.RUN_ID.reset, run)
        self.task = "Resume a bounded checkpoint fixture"
        self.turns = [{"role": "assistant", "content": "Retained conversation"}]
        self.row = {"agent": "worker", "tool": "read_file", "arguments": '{"path":"fixture.txt"}',
                    "result": "retained 漢字 \" result\n" * 100}

    def save(self):
        self.h.save_checkpoint(self.task, "Retained summary", self.turns)
        return json.loads(self.h.checkpoint_file(self.task).read_text(encoding="utf-8"))

    def journal(self, state):
        return self.h.checkpoint_file(self.task).with_name(
            f"checkpoint-fixture-{state['evidence']['journal']}.evidence.jsonl")

    def inspect(self, state):
        return self.h.EvidenceJournal(self.h.checkpoint_file(self.task)).restore(state["evidence"])

    def fresh_budget(self):
        budget = self.h.RunBudget(self.h.EFFORTS["medium"])
        token = self.h.BUDGET.set(budget)
        self.addCleanup(self.h.BUDGET.reset, token)
        return budget

    def test_checkpoint_size_does_not_follow_retained_evidence_size(self):
        self.budget.observations = [dict(self.row)]
        first = self.save()
        initial_size = self.h.checkpoint_file(self.task).stat().st_size
        self.budget.observations.extend(dict(self.row) for _ in range(999))
        final = self.save()
        self.assertTrue("observations" not in final)
        self.assertEqual(final["turns"], self.turns)
        self.assertEqual(final["summary"], "Retained summary")
        self.assertLess(self.h.checkpoint_file(self.task).stat().st_size, initial_size + 10)
        self.assertGreater(self.journal(final).stat().st_size, 1_000_000)
        self.assertEqual(first["evidence"]["journal"], final["evidence"]["journal"])
        self.assertEqual(self.inspect(final), self.budget.observations)

    def test_saves_append_each_observation_once_including_identical_records(self):
        self.budget.observations = [dict(self.row)]
        first = self.save()
        prefix = self.journal(first).read_bytes()
        self.budget.observations.append(dict(self.row))
        final = self.save()
        self.assertEqual(self.journal(final).read_bytes(), prefix + prefix)
        self.assertEqual(final["evidence"]["records"], 2)
        self.assertEqual(final["evidence"]["sha256"], hashlib.sha256(prefix + prefix).hexdigest())
        self.save()
        self.assertEqual(self.journal(final).read_bytes(), prefix + prefix)

    def test_same_budget_resume_does_not_duplicate_or_reset_accounting(self):
        self.budget.observations = [dict(self.row), dict(self.row)]
        self.budget.tokens, self.budget.cost, self.budget.workers = 123, 0.25, 1
        deadline = self.budget.deadline
        state = self.save()
        self.assertEqual(self.h.load_checkpoint(self.task), state)
        self.assertEqual(self.h.load_checkpoint(self.task), state)
        self.assertEqual(self.budget.observations, [self.row, self.row])
        self.assertEqual((self.budget.tokens, self.budget.cost, self.budget.workers), (123, 0.25, 1))
        self.assertEqual(self.budget.deadline, deadline)

    def test_fresh_budget_resume_loads_complete_evidence_and_reuses_journal(self):
        self.budget.observations = [dict(self.row)]
        original = self.save()
        budget = self.fresh_budget()
        self.h.load_checkpoint(self.task)
        self.assertEqual(budget.observations, [self.row])
        budget.observations.append(dict(self.row))
        final = self.save()
        self.assertEqual(original["evidence"]["journal"], final["evidence"]["journal"])
        self.assertEqual(self.inspect(final), [self.row, self.row])
        self.assertEqual(self.inspect(original), [self.row])

    def test_fresh_process_can_resume_without_model_or_workspace_reads(self):
        self.budget.observations = [dict(self.row)]
        self.save()
        code = ("import json, mini_harness as h; h.RUN_ID.set('checkpoint-fixture'); "
                "h.BUDGET.set(h.RunBudget(h.EFFORTS['medium'])); "
                f"h.load_checkpoint({self.task!r}); "
                "print(json.dumps(h.BUDGET.get().observations)); h.client.close()")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "harness"), LLM_API_KEY="EMPTY",
                   LLM_BASE_URL="http://127.0.0.1:9/v1", AGENT_MAX_COST_USD="0",
                   AGENT_CHECKPOINTS=str(self.h.CHECKPOINT_DIR),
                   NO_PROXY="localhost,.localhost,127.0.0.1,::1",
                   no_proxy="localhost,.localhost,127.0.0.1,::1")
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [self.row])

    def test_json_string_surrogates_and_clipping_markers_survive_resume(self):
        row = self.row | {"arguments": '{"content":"\ud800"}',
                          "result": "Retained \udfff text ... [100 characters clipped]"}
        self.budget.observations = [row]
        state = self.save()
        budget = self.fresh_budget()
        self.h.load_checkpoint(self.task)
        self.assertEqual(budget.observations, [row])
        self.assertEqual(self.inspect(state), [row])

    def test_missing_journal_stops_resume_before_model_or_tools(self):
        self.budget.observations = [dict(self.row)]
        state = self.save()
        self.journal(state).rename(self.journal(state).with_suffix(".held"))
        with self.assertRaisesRegex(ValueError, "evidence.*unavailable"):
            self.h.run_agent(self.task, "fixture", [], effort="medium", resume=True)
        self.h.call_model.assert_not_called()

    def test_modified_journal_is_rejected_without_loading_evidence(self):
        self.budget.observations = [dict(self.row)]
        state = self.save()
        self.journal(state).write_bytes(self.journal(state).read_bytes().replace(b"retained", b"tampered"))
        budget = self.fresh_budget()
        with self.assertRaisesRegex(ValueError, "evidence.*digest"):
            self.h.load_checkpoint(self.task)
        self.assertEqual(budget.observations, [])

    def test_truncated_and_malformed_journals_are_rejected(self):
        self.budget.observations = [dict(self.row)]
        state = self.save()
        original = self.journal(state).read_bytes()
        for data in (b"", original[:-1], b"not-json\n", b"\xff\n"):
            with self.subTest(data=data[:10]):
                self.journal(state).write_bytes(data)
                with self.assertRaisesRegex(ValueError, "evidence"):
                    self.h.load_checkpoint(self.task)

    def test_invalid_reference_cannot_select_arbitrary_files(self):
        state = self.save()
        original = state["evidence"]
        for key, value in (("journal", "../private"), ("journal", "f" * 31),
                           ("records", True), ("records", -1), ("records", "0"),
                           ("sha256", "not-a-digest")):
            with self.subTest(key=key, value=value):
                state["evidence"] = original | {key: value}
                self.h.checkpoint_file(self.task).write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "evidence.*reference"):
                    self.h.load_checkpoint(self.task)

    def test_valid_digest_does_not_allow_invalid_observation_schema(self):
        state = self.save()
        for row in ({"agent": "worker"}, self.row | {"result": ["not text"]},
                    self.row | {"thought": "not review evidence"}):
            with self.subTest(row=row):
                data = (json.dumps(row) + "\n").encode()
                self.journal(state).write_bytes(data)
                state["evidence"].update(records=1, sha256=hashlib.sha256(data).hexdigest())
                self.h.checkpoint_file(self.task).write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "evidence.*record"):
                    self.h.load_checkpoint(self.task)

    def test_uncommitted_crash_tail_is_preserved_but_not_resumed(self):
        self.budget.observations = [dict(self.row)]
        original = self.save()
        with self.journal(original).open("ab") as stream:
            stream.write(b'{"partial":')
        original_bytes = self.journal(original).read_bytes()
        budget = self.fresh_budget()
        self.h.load_checkpoint(self.task)
        self.assertEqual(budget.observations, [self.row])
        budget.observations.append(dict(self.row))
        final = self.save()
        self.assertNotEqual(original["evidence"]["journal"], final["evidence"]["journal"])
        self.assertEqual(self.journal(original).read_bytes(), original_bytes)
        self.assertEqual(self.inspect(final), [self.row, self.row])

    def test_checkpoint_publish_failure_preserves_previous_committed_prefix(self):
        self.budget.observations = [dict(self.row)]
        original = self.save()
        self.budget.observations.append(dict(self.row))
        with patch.object(Path, "replace", side_effect=OSError("fixture publication failure")):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(json.loads(self.h.checkpoint_file(self.task).read_text()), original)
        self.assertEqual(self.inspect(original), [self.row])
        budget = self.fresh_budget()
        self.h.load_checkpoint(self.task)
        self.assertEqual(budget.observations, [self.row])

    def test_conflicting_in_memory_evidence_is_not_silently_replaced(self):
        self.budget.observations = [dict(self.row)]
        self.save()
        self.budget.observations[0] = self.row | {"result": "different task evidence"}
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.h.load_checkpoint(self.task)
        self.assertEqual(self.budget.observations[0]["result"], "different task evidence")

    def test_same_budget_uncommitted_observations_are_not_discarded(self):
        self.budget.observations = [dict(self.row)]
        self.save()
        self.budget.observations.append(self.row | {"result": "later observation"})
        self.h.load_checkpoint(self.task)
        self.assertEqual(len(self.budget.observations), 2)
        self.assertEqual(self.inspect(self.save()), self.budget.observations)

    def test_wrong_task_and_unsupported_checkpoint_fail_before_model(self):
        state = self.save()
        for changes in ({"task": "another task"}, {"format": 999}):
            with self.subTest(changes=changes):
                self.h.checkpoint_file(self.task).write_text(json.dumps(state | changes), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "checkpoint|Checkpoint"):
                    self.h.run_agent(self.task, "fixture", [], effort="medium", resume=True)
        self.h.call_model.assert_not_called()

    def test_real_escalation_retains_two_actual_identical_observations_not_three(self):
        (self.h.WORKSPACE / "fixture.txt").write_text("actual result", encoding="utf-8")
        call = {"id": "fixture-call", "name": "read_file", "arguments": '{"path":"fixture.txt"}'}
        with patch.object(self.h, "MAX_STEPS", 1), patch.object(
                self.h, "call_model", side_effect=[self.h.Reply("", [call]), self.h.Reply("", [call])]):
            result = self.h.run_escalating(self.task, "fixture", ["read_file"], start="low", stop="medium")
        self.assertTrue(result.startswith("Stopped at the 1-step limit"))
        self.assertEqual(len(self.budget.observations), 2)
        self.assertEqual(self.budget.observations[0], self.budget.observations[1])
        state = json.loads(self.h.checkpoint_file(self.task).read_text())
        self.assertEqual(self.inspect(state), self.budget.observations)


if __name__ == "__main__":
    unittest.main()
