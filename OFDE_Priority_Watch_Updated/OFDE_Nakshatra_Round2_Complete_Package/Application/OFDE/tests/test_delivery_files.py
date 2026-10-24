"""Static delivery checks (code inspection, NOT Windows execution): referenced files exist, configs parse, docs match the project."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class TestDelivery(unittest.TestCase):
    def test_required_files_exist(self):
        for rel in ("README.md", "ARCHITECTURE.md", "SCIENTIFIC_METHOD.md", "API_REFERENCE.md", "KNOWN_LIMITATIONS.md", "TEST_REPORT.md",
                    "PRESENTER_GUIDE.md", "DELIVERY_MANIFEST.md", "TROUBLESHOOTING.md", "DATA_DICTIONARY.md", "requirements.txt",
                    "requirements-dev.txt", ".env.example", ".gitignore", "start_ofde.ps1", ".vscode/settings.json", ".vscode/tasks.json",
                    ".vscode/launch.json", "frontend/index.html", "data/demo_synthetic.json", "tools/verify_sgp4.py", "tools/tune_demo_sgp4.py",
                    "tools/e2e_real_backend.py", "tools/ui_smoke_test.py", "ofde/__main__.py"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_powershell_script_references_existing_files_and_stops_on_failure(self):
        ps = read("start_ofde.ps1")
        for rel in re.findall(r"tools\\\\?([A-Za-z0-9_]+\.py)", ps):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "tools", rel)), rel)
        for f in ("requirements.txt", "requirements-dev.txt"):
            self.assertIn(f, ps)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, f)))
        # every native call goes through Invoke-Native and each result is followed by a Fail (exit 1) branch
        self.assertEqual(len(re.findall(r"=\s*Invoke-Native", ps)), 7)   # python check, venv, pip, pytest, verify, e2e, server
        for step in ("pip install failed", "Tests failed", "SGP4 verification failed", "End-to-end check reported failures", "Could not create .venv", "server exited with code"):
            self.assertIn(step, ps)
        self.assertIn('function Fail([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }', ps)
        self.assertEqual(len(re.findall(r"&\s+\$", ps)), 1)     # the only raw native call lives inside Invoke-Native
        self.assertTrue(ps.isascii())
        self.assertNotRegex(ps, r"Set-ExecutionPolicy\s+-Scope\s+(LocalMachine|CurrentUser)")   # never change persistent policy
        self.assertEqual(ps.count("{"), ps.count("}"))
        self.assertEqual(ps.count("("), ps.count(")"))

    def test_vscode_configs_parse_and_reference_existing_scripts(self):
        for f in (".vscode/settings.json", ".vscode/tasks.json", ".vscode/launch.json", ".vscode/extensions.json"):
            json.loads(read(f))
        tasks = json.loads(read(".vscode/tasks.json"))["tasks"]
        for t in tasks:
            for rel in re.findall(r"(?:tools|\.)\\\\?([A-Za-z0-9_]+\.(?:py|ps1))", t["command"]):
                path = os.path.join(ROOT, rel) if rel.endswith(".ps1") else os.path.join(ROOT, "tools", rel)
                self.assertTrue(os.path.isfile(path), (t["label"], rel))

    def test_readme_commands_match_project(self):
        md = read("README.md")
        for needle in ("start_ofde.ps1", "python -m ofde", "tools\\verify_sgp4.py", "http://127.0.0.1:8000", "requirements-dev.txt", "pytest"):
            self.assertIn(needle, md)
        self.assertIn("Node.js is **not required**", md)
        for rel in re.findall(r"`(tools[\\/][A-Za-z0-9_]+\.py)`", md):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel.replace("\\", os.sep))), rel)

    def test_no_node_requirement(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "package.json")))
        self.assertNotIn("npm install", read("README.md").replace("npm errors", ""))

    def test_gitignore_excludes_generated_files(self):
        gi = read(".gitignore")
        for pat in (".venv/", "__pycache__/", "*.sqlite3", ".env", "data/sgp4_verification.json", "e2e_results.json"):
            self.assertIn(pat, gi)

    def test_frontend_labels_illustrative_hero_and_computed_results(self):
        html = read("frontend/index.html")
        self.assertIn("Illustrative scene. Not generated from computed data.", html)
        self.assertIn("ILLUSTRATIVE, NOT COMPUTED", html)
        self.assertIn("COMPUTED", html)
        self.assertNotIn("Math.random", html)    # no fabricated numbers; starfield uses a seeded generator


if __name__ == "__main__":
    unittest.main()
