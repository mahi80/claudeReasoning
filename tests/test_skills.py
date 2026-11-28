import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MANIFEST = json.loads((SKILLS / "provenance.json").read_text(encoding="utf-8"))
BUILTIN = {"adr", "cloud-choice", "coding-conventions", "delivery-workflow",
           "feature-planning", "github-actions", "report-style", "sonarqube"}
IMPORTED = {"docx", "xlsx", "pdf", "pptx", "ponytail", "systematic-debugging",
            "test-driven-development", "verification-before-completion", "code-review",
            "frontend-design", "webapp-testing", "mcp-builder", "vercel-react-best-practices",
            "web-design-guidelines", "api-design", "database-migrations", "docker-patterns",
            "security-review", "python-testing", "terraform-style-guide", "terraform-test",
            "aws-cdk", "aws-containers", "aws-billing-and-cost-management", "azure-prepare",
            "azure-diagnostics", "cloud-run", "workers-best-practices", "k8s-manifest-generator",
            "distributed-tracing", "agent-evaluation", "ai-prompt-regression-testing",
            "agent-evaluation-reporting"}


def metadata(text):
    header = text.split("---", 2)[1]
    return dict(line.split(":", 1) for line in header.splitlines() if ":" in line)


class SkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_env = {key: os.environ.get(key) for key in
                       ("AGENT_WORKSPACE", "AGENT_SKILLS", "AGENT_TRACE", "LLM_API_KEY")}
        os.environ.update(AGENT_WORKSPACE=cls.tmp.name, AGENT_SKILLS=str(SKILLS),
                          AGENT_TRACE=str(Path(cls.tmp.name) / "trace.jsonl"), LLM_API_KEY="EMPTY")
        sys.path.insert(0, str(ROOT / "harness"))
        import mini_harness
        cls.h = mini_harness

    @classmethod
    def tearDownClass(cls):
        cls.h.client.close()
        for key, value in cls.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.tmp.cleanup()

    def test_inventory_matches_manifest_and_original_skills(self):
        names = [name for source in MANIFEST["sources"] for name in source["skills"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), IMPORTED)
        self.assertEqual({p.parent.name for p in SKILLS.glob("*/SKILL.md")}, IMPORTED | BUILTIN)

    def test_frontmatter_is_compatible_with_actual_loader(self):
        for name in IMPORTED | BUILTIN:
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                meta = metadata(text)
                self.assertEqual(meta["name"].strip(), name)
                description = meta["description"].strip()
                self.assertTrue(description and description not in {"|", ">"})
                self.assertLessEqual(len(description), 1024)
                self.assertRegex(name, r"^[a-z0-9-]+$")

    def test_bodies_are_small_and_load_without_clipping(self):
        for name in IMPORTED | BUILTIN:
            with self.subTest(skill=name):
                path = SKILLS / name / "SKILL.md"
                self.assertLess(path.stat().st_size, 4500)
                text = path.read_text(encoding="utf-8")
                self.assertEqual(self.h.load_skill(name), text)
                self.assertLess(len(text), self.h.REGISTRY["load_skill"].max_chars)
                self.assertEqual(self.h.clip(text, self.h.REGISTRY["load_skill"].max_chars), text)

    def test_imported_descriptions_are_not_in_the_initial_prompt(self):
        index = self.h.skills_index()
        self.assertEqual(len(index.splitlines()), len(BUILTIN) + 1)
        self.assertLess(len(index.encode("utf-8")), 1500)
        self.assertIn("find_skills", index)
        for name in BUILTIN:
            self.assertTrue(any(line.startswith(f"- {name}: ") for line in index.splitlines()))
        system = self.h.orchestrator_system()
        for name in IMPORTED:
            self.assertNotIn(f"- {name}: ", system)
        with patch.object(self.h, "skill_description", wraps=self.h.skill_description) as reader:
            self.h.skills_index()
        self.assertEqual({call.args[0].parent.name for call in reader.call_args_list}, BUILTIN)

    def test_discovery_searches_names_and_descriptions_then_loads_instructions(self):
        for query, expected in (("WORD", "docx"), ("xlsx", "xlsx"), ("terraform test", "terraform-test")):
            with self.subTest(query=query):
                result = json.loads(self.h.find_skills(query))
                self.assertIn(expected, {row["name"] for row in result["skills"]})
                self.assertEqual(self.h.load_skill(expected),
                                 (SKILLS / expected / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(self.h.find_skills("no-such-skill")),
                         {"skills": [], "total": 0, "next_offset": None})

    def test_discovery_pagination_is_bounded_complete_and_unclipped(self):
        names, offset = [], 0
        while offset is not None:
            text = self.h.find_skills("", offset)
            self.assertLessEqual(len(text.encode("utf-8")), 3500)
            self.assertEqual(self.h.clip(text, self.h.REGISTRY["find_skills"].max_chars), text)
            result = json.loads(text)
            self.assertEqual(result["total"], len(IMPORTED | BUILTIN))
            self.assertLessEqual(len(result["skills"]), 5)
            names.extend(row["name"] for row in result["skills"])
            following = result["next_offset"]
            self.assertTrue(following is None or following > offset)
            offset = following
        self.assertEqual(names, sorted(IMPORTED | BUILTIN))
        self.assertEqual(json.loads(self.h.find_skills("", 100))["skills"], [])

    def test_discovery_rejects_invalid_queries_and_offsets(self):
        for query, offset in ((None, 0), ("x" * 201, 0), ("", -1), ("", True), ("", 1.5)):
            with self.subTest(query=query, offset=offset):
                self.assertTrue(self.h.find_skills(query, offset).startswith("ERROR:"))
        schema = self.h.REGISTRY["find_skills"].parameters
        self.assertEqual(schema["required"], ["query", "offset"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["offset"], {"type": "integer", "minimum": 0})

    def test_custom_skills_stay_visible_without_a_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skill = root / "custom"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: custom\ndescription: Local workflow\n---\nBody",
                                          encoding="utf-8")
            with patch.object(self.h, "SKILLS_DIR", root):
                self.assertEqual(self.h.skills_index(), "- custom: Local workflow")
                self.assertNotIn("find_skills", self.h.skills_index())
                self.assertEqual(json.loads(self.h.find_skills("local"))["skills"][0]["name"], "custom")

    def test_custom_skills_stay_visible_alongside_the_imported_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "provenance.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
            skill = root / "custom"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: custom\ndescription: Local workflow\n---\nBody",
                                          encoding="utf-8")
            with patch.object(self.h, "SKILLS_DIR", root):
                self.assertEqual(self.h.skills_index(), "- custom: Local workflow")

    def test_long_unicode_discovery_pages_still_make_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(10):
                skill = root / f"unicode-{number}"
                skill.mkdir()
                (skill / "SKILL.md").write_text("---\ndescription: " + "\u4e2d" * 1024 + "\n---\nBody",
                                              encoding="utf-8")
            names, offset = [], 0
            with patch.object(self.h, "SKILLS_DIR", root):
                while offset is not None:
                    text = self.h.find_skills("", offset)
                    self.assertLessEqual(len(text.encode("utf-8")), 3500)
                    result = json.loads(text)
                    self.assertTrue(result["skills"])
                    names.extend(row["name"] for row in result["skills"])
                    following = result["next_offset"]
                    self.assertTrue(following is None or following > offset)
                    offset = following
            self.assertEqual(len(names), 10)

    def test_worker_discovery_requires_an_explicit_parent_grant(self):
        budget = self.h.RunBudget(self.h.EFFORTS["medium"])
        token = self.h.BUDGET.set(budget)
        scope = self.h.TOOL_SCOPE.set(("load_skill",))
        try:
            with patch.object(self.h, "run_agent", return_value="worker done") as runner:
                self.assertTrue(self.h.spawn_agent("look up skills", ["find_skills"]).startswith("ERROR:"))
                runner.assert_not_called()
                self.assertEqual(self.h.spawn_agent("load a named skill", ["load_skill"]), "worker done")
                self.assertNotIn("find_skills", runner.call_args.args[1])
                self.assertNotIn("- docx: ", runner.call_args.args[1])
                self.assertEqual(runner.call_args.args[2], ["load_skill"])
            self.h.TOOL_SCOPE.reset(scope)
            scope = self.h.TOOL_SCOPE.set(("load_skill", "find_skills"))
            with patch.object(self.h, "run_agent", return_value="worker done") as runner:
                self.assertEqual(self.h.spawn_agent("look up a Word workflow", ["load_skill", "find_skills"]),
                                 "worker done")
                self.assertIn("find_skills", runner.call_args.args[1])
                self.assertNotIn("- docx: ", runner.call_args.args[1])
                self.assertEqual(runner.call_args.args[2], ["load_skill", "find_skills"])
        finally:
            self.h.TOOL_SCOPE.reset(scope)
            self.h.BUDGET.reset(token)

    def test_discovery_does_not_grant_execution_tools(self):
        before = tuple(self.h.REGISTRY)
        scope = self.h.TOOL_SCOPE.set(("find_skills", "load_skill"))
        try:
            self.h.find_skills("cloud")
            self.h.load_skill("aws-cdk")
            self.assertEqual(self.h.TOOL_SCOPE.get(), ("find_skills", "load_skill"))
            self.assertTrue(self.h.spawn_agent("deploy", ["run_shell"]).startswith("ERROR:"))
        finally:
            self.h.TOOL_SCOPE.reset(scope)
        self.assertEqual(tuple(self.h.REGISTRY), before)

    def test_agent_discovers_and_loads_an_import_through_the_tool_loop(self):
        requests = []

        def model(messages, tools, max_tokens, extra):
            requests.append(messages)
            self.assertEqual({tool.name for tool in tools}, {"find_skills", "load_skill"})
            self.assertNotIn("- docx: ", messages[0]["content"])
            if len(requests) == 1:
                return self.h.Reply("", [{"id": "find", "name": "find_skills",
                                         "arguments": json.dumps({"query": "word", "offset": 0})}])
            if len(requests) == 2:
                self.assertIn("docx", {row["name"] for row in json.loads(messages[-1]["content"])["skills"]})
                return self.h.Reply("", [{"id": "load", "name": "load_skill",
                                         "arguments": json.dumps({"name": "docx"})}])
            self.assertIn("# Word documents (.docx)", messages[-1]["content"])
            return self.h.Reply("Loaded the Word workflow without executing a command.", [])

        with patch.object(self.h, "call_model", side_effect=model), \
                patch.object(self.h, "CHECKPOINT_DIR", Path(self.tmp.name) / "checkpoints"):
            answer = self.h.run_agent("Prepare a Word document workflow", self.h.orchestrator_system(),
                                      ["find_skills", "load_skill"], effort="medium")
        self.assertEqual(answer, "Loaded the Word workflow without executing a command.")
        self.assertEqual(len(requests), 3)

    def test_root_notice_covers_sources_licenses_and_attribution(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        for source in MANIFEST["sources"]:
            self.assertIn(source["repository"], notice)
            for path in source["license_files"]:
                self.assertIn("skills/" + path, notice)
        for text in ("MPL-2.0", "CC-BY-4.0", "Apache-2.0", "MIT", "Vibeship", "Ranjeet2063",
                     "Whxuan0701", "2026-09-05", "skills/THIRD_PARTY_NOTICES.md"):
            self.assertIn(text, notice)
        self.assertIn((SKILLS / "licenses/aws-NOTICE.txt").read_text().strip(), notice)

    def test_source_revisions_paths_and_frontmatter_match(self):
        for source in MANIFEST["sources"]:
            self.assertRegex(source["revision"], r"^[0-9a-f]{40}$")
            for name, path in source["skills"].items():
                with self.subTest(skill=name):
                    base = f"https://github.com/{source['repository']}"
                    route = (f"/tree/{source['revision']}/{PurePosixPath(path).parent}"
                             if path.endswith("SKILL.md") else f"/blob/{source['revision']}/{path}")
                    meta = metadata((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
                    self.assertEqual(meta["source"].strip(), base + route)
                    self.assertIn("adapted", meta["license"])
                    self.assertIn("skills/THIRD_PARTY_NOTICES.md", meta["license"])

    def test_license_resources_are_confined_and_nonempty(self):
        for source in MANIFEST["sources"]:
            for relative in source["license_files"]:
                path = (SKILLS / relative).resolve()
                self.assertIn(SKILLS.resolve(), path.parents)
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 50)
        self.assertIn("Amazon.com", (SKILLS / "licenses/aws-NOTICE.txt").read_text())
        self.assertIn("Mozilla Public License", (SKILLS / "licenses/terraform-MPL-2.0.txt").read_text())
        self.assertGreater((SKILLS / "licenses/CC-BY-4.0.txt").stat().st_size, 10000)

    def test_attribution_links_resolve_locally(self):
        notice = (SKILLS / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", notice):
            if not target.startswith("https://"):
                self.assertTrue((SKILLS / target).is_file(), target)
        for name in IMPORTED:
            self.assertIn(name, notice)
        for author in ("Ranjeet2063", "Whxuan0701", "Vibeship", "2026-09-05"):
            self.assertIn(author, notice)

    def test_mpl_notices_remain_in_adapted_files(self):
        for name in ("terraform-test", "terraform-style-guide"):
            text = self.h.load_skill(name)
            self.assertIn("Mozilla Public License", text)
            self.assertIn("licenses/terraform-MPL-2.0.txt", text)

    def test_import_is_instruction_only_and_preserves_tool_registry(self):
        before = tuple(self.h.REGISTRY)
        for name in IMPORTED:
            path = SKILLS / name
            self.assertEqual({p.name for p in path.iterdir()}, {"SKILL.md"})
            text = self.h.load_skill(name)
            self.assertTrue(text.isascii(), name)
            self.assertRegex(text.lower(), r"approv|authoriz|operator")
        self.assertEqual(tuple(self.h.REGISTRY), before)
        self.assertTrue(self.h.load_skill("../README").startswith("ERROR:"))


if __name__ == "__main__":
    unittest.main()
