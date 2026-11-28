import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import unittest

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

    def test_descriptions_are_indexed_once_with_bounded_prompt_cost(self):
        index = self.h.skills_index()
        self.assertEqual(len(index.splitlines()), len(IMPORTED | BUILTIN))
        self.assertLess(len(index), 10000)
        for name in IMPORTED | BUILTIN:
            self.assertTrue(any(line.startswith(f"- {name}: ") for line in index.splitlines()))

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
