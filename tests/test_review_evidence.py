from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))


class ReviewEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="review-evidence-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        with patch.dict(os.environ, {"LLM_API_KEY": "EMPTY", "LLM_BASE_URL": "http://127.0.0.1:9/v1",
                                     "AGENT_WORKSPACE": str(root / "workspace"),
                                     "AGENT_TRACE": str(root / "trace.jsonl"),
                                     "AGENT_CHECKPOINTS": str(root / "checkpoints"),
                                     "AGENT_MAX_COST_USD": "0"}):
            cls.h = importlib.import_module("mini_harness")
        cls.addClassCleanup(cls.h.client.close)

    def setUp(self):
        self.budget = self.h.RunBudget(self.h.EFFORTS["xhigh"])
        self.budget.observations = [{"agent": "worker", "tool": "read_file",
                                     "arguments": json.dumps({"path": f"fixture-{n}.txt"}),
                                     "result": "retained result " * 20} for n in range(45)]
        budget = self.h.BUDGET.set(self.budget)
        scope = self.h.TOOL_SCOPE.set(("read_file", "list_dir", "think", "list_evidence", "read_evidence"))
        self.addCleanup(self.h.BUDGET.reset, budget)
        self.addCleanup(self.h.TOOL_SCOPE.reset, scope)

    def enable_evidence(self):
        token = self.h.REVIEW_EVIDENCE.set(tuple(dict(row) for row in self.budget.observations))
        self.addCleanup(self.h.REVIEW_EVIDENCE.reset, token)

    def test_long_review_uses_metadata_instead_of_clipping(self):
        with patch.object(self.h, "run_agent", return_value="PASS") as agent:
            self.assertEqual(self.h.review("review fixture", "answer", "xhigh"), "PASS")
        brief, system, tools = agent.call_args.args[:3]
        metadata = json.loads(brief.split("\n\n[Runtime-observed tool activity]\n", 1)[1])
        self.assertEqual(metadata["total_records"], 45)
        self.assertLess(len(brief.encode("utf-8")), 6000)
        self.assertEqual(set(tools), {"read_file", "list_dir", "think", "list_evidence", "read_evidence"})
        self.assertIn("retained", system)

    def test_small_review_keeps_complete_inline_evidence(self):
        self.budget.observations = self.budget.observations[:1]
        with patch.object(self.h, "run_agent", return_value="PASS") as agent:
            self.h.review("review fixture", "answer", "xhigh")
        brief = agent.call_args.args[0]
        self.assertEqual(json.loads(brief.split("\n\n[Runtime-observed tool activity]\n", 1)[1]),
                         self.budget.observations)

    def test_evidence_tools_are_not_coordinator_or_worker_capabilities(self):
        for name in ("list_evidence", "read_evidence"):
            self.assertNotIn(name, self.h.ORCHESTRATOR_TOOLS)
            self.assertNotIn(name, self.h.WORKER_TOOLS)
            tool = self.h.REGISTRY[name]
            self.assertFalse(tool.needs_approval)
            self.assertTrue(tool.parallel)
            self.assertNotEqual(tool.fn, self.h.write_file)
        self.assertTrue(self.h.list_evidence(0).startswith("ERROR:"))
        self.assertTrue(self.h.read_evidence(0, 0).startswith("ERROR:"))

    def test_index_pages_are_bounded_and_cover_every_record(self):
        self.enable_evidence()
        offset, indices = 0, []
        with patch.object(self.h, "MAX_TOOL_CHARS", 512):
            while offset is not None:
                text = self.h.list_evidence(offset)
                self.assertLessEqual(len(text.encode("utf-8")), 512)
                page = json.loads(text)
                indices.extend(item["index"] for item in page["items"])
                self.assertEqual(page["total_records"], 45)
                self.assertNotIn("result", page["items"][0])
                if page["next_offset"] is not None:
                    self.assertGreater(page["next_offset"], offset)
                offset = page["next_offset"]
        self.assertEqual(indices, list(range(45)))

    def test_json_string_surrogates_can_be_indexed_and_read(self):
        self.budget.observations = [{"agent": "worker\ud800", "tool": "read_file",
                                     "arguments": '{"path":"\udfff"}', "result": "Retained \ud800 text"}]
        self.enable_evidence()
        self.assertEqual(json.loads(self.h.list_evidence(0))["items"][0]["agent"], "worker\ud800")
        page = json.loads(self.h.read_evidence(0, 0))
        self.assertEqual(json.loads(page["content"]), self.budget.observations[0])
        self.assertIsNone(page["next_offset"])
        with patch.object(self.h, "run_agent", return_value="PASS") as agent:
            self.h.review("review fixture", "answer", "xhigh")
        activity = agent.call_args.args[0].split("\n\n[Runtime-observed tool activity]\n", 1)[1]
        self.assertEqual(json.loads(activity), self.budget.observations)

    def test_record_pages_preserve_unicode_and_json_without_tool_clipping(self):
        self.budget.observations[0]["arguments"] = json.dumps({"content": "漢\\\"\t" * 7000}, ensure_ascii=False)
        self.enable_evidence()
        offset, chunks = 0, []
        while offset is not None:
            call = {"name": "read_evidence", "arguments": json.dumps({"index": 0, "offset": offset})}
            text = self.h.execute(call, self.h.REGISTRY, Counter())
            self.assertLessEqual(len(text.encode("utf-8")), self.h.MAX_TOOL_CHARS)
            page = json.loads(text)
            self.assertEqual(page["offset"], offset)
            chunks.append(page["content"])
            if page["next_offset"] is not None:
                self.assertGreater(page["next_offset"], offset)
                self.assertEqual(page["next_offset"], offset + len(page["content"]))
            offset = page["next_offset"]
        self.assertEqual(json.loads("".join(chunks)), self.budget.observations[0])

    def test_tiny_pages_fail_instead_of_returning_stalled_cursors(self):
        self.enable_evidence()
        total = len(json.dumps(self.budget.observations[0], ensure_ascii=False))
        empty = json.dumps({"index": 0, "offset": 0, "total_chars": total,
                            "content": "", "next_offset": 0}, ensure_ascii=False)
        with patch.object(self.h, "MAX_TOOL_CHARS", len(empty.encode("utf-8"))):
            self.assertTrue(self.h.read_evidence(0, 0).startswith("ERROR:"))

    def test_empty_index_and_terminal_record_cursor_are_complete(self):
        self.enable_evidence()
        total = len(json.dumps(self.budget.observations[0], ensure_ascii=False))
        page = json.loads(self.h.read_evidence(0, total))
        self.assertEqual(page["content"], "")
        self.assertIsNone(page["next_offset"])
        self.h.REVIEW_EVIDENCE.set(())
        self.assertEqual(json.loads(self.h.list_evidence(0)),
                         {"total_records": 0, "items": [], "next_offset": None})

    def test_concurrent_reviews_do_not_share_snapshots(self):
        barrier = threading.Barrier(2)

        def inspect(*args, **kwargs):
            barrier.wait(timeout=2)
            row = json.loads(json.loads(self.h.read_evidence(0, 0))["content"])
            return row["result"]

        def review(tag):
            budget = self.h.RunBudget(self.h.EFFORTS["xhigh"])
            budget.observations = [{**self.budget.observations[0], "result": tag}]
            token = self.h.BUDGET.set(budget)
            scope = self.h.TOOL_SCOPE.set(("read_evidence", "list_evidence"))
            try:
                result = self.h.review(tag, "answer", "xhigh")
                self.assertIsNone(self.h.REVIEW_EVIDENCE.get())
                return result
            finally:
                self.h.TOOL_SCOPE.reset(scope)
                self.h.BUDGET.reset(token)

        with patch.object(self.h, "run_agent", side_effect=inspect), ThreadPoolExecutor(2) as pool:
            tasks = [pool.submit(review, tag) for tag in ("first", "second")]
            self.assertEqual([task.result(timeout=3) for task in tasks], ["first", "second"])

    def test_invalid_cursors_are_rejected(self):
        self.enable_evidence()
        for offset in (-1, 46, True, "0"):
            self.assertTrue(self.h.list_evidence(offset).startswith("ERROR:"))
        for index, offset in ((-1, 0), (45, 0), (True, 0), (0, -1), (0, True), (0, 1000000)):
            self.assertTrue(self.h.read_evidence(index, offset).startswith("ERROR:"))

    def test_review_snapshot_is_stable_and_resets_on_exception(self):
        old = self.h.REVIEW_EVIDENCE.get()
        original = dict(self.budget.observations[0])

        def inspect(*args, **kwargs):
            snapshot = self.h.REVIEW_EVIDENCE.get()
            self.budget.observations[0]["result"] = "later mutation"
            self.assertEqual(snapshot[0], original)
            raise RuntimeError("fixture reviewer failure")

        with patch.object(self.h, "run_agent", side_effect=inspect):
            with self.assertRaisesRegex(RuntimeError, "fixture reviewer failure"):
                self.h.review("review fixture", "answer", "xhigh")
        self.assertIs(self.h.REVIEW_EVIDENCE.get(), old)

    def test_evidence_access_requires_scope_and_honors_shared_deadline(self):
        self.enable_evidence()
        scope = self.h.TOOL_SCOPE.set(("read_file",))
        try:
            self.assertTrue(self.h.list_evidence(0).startswith("ERROR:"))
            self.assertTrue(self.h.read_evidence(0, 0).startswith("ERROR:"))
        finally:
            self.h.TOOL_SCOPE.reset(scope)
        self.budget.deadline = time.monotonic() - 1
        with self.assertRaises(self.h.BudgetExceeded):
            self.h.list_evidence(0)
        with self.assertRaises(self.h.BudgetExceeded):
            self.h.read_evidence(0, 0)

    def test_paging_retains_incomplete_markers_and_does_not_mutate_history(self):
        self.budget.observations[0]["result"] = self.h.clip("fixture output " * 100, 32)
        self.enable_evidence()
        original = json.dumps(self.budget.observations)
        page = json.loads(self.h.read_evidence(0, 0))
        row = json.loads(page["content"])
        self.assertIn("characters clipped", row["result"])
        self.assertEqual(json.dumps(self.budget.observations), original)


if __name__ == "__main__":
    unittest.main()
