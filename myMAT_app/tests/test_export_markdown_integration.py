from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_KNOWLEDGE_ROOT = REPO_ROOT / "myMAT_knowledge"


class ExportMarkdownIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not REAL_KNOWLEDGE_ROOT.exists():
            self.skipTest(f"Knowledge root not found: {REAL_KNOWLEDGE_ROOT}")

    def _run_cli(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "myMAT_app.parser.export_markdown", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_real_knowledge_base_exports_one_markdown_per_top_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "markdown"
            report_path = Path(tmp) / "report.json"
            proc = self._run_cli(
                [
                    "--knowledge-root",
                    str(REAL_KNOWLEDGE_ROOT),
                    "--output-dir",
                    str(output_dir),
                    "--report-path",
                    str(report_path),
                ],
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("Markdown Export Summary", proc.stdout)
            self.assertTrue(report_path.exists())

            top_folders = sorted(path.name for path in REAL_KNOWLEDGE_ROOT.iterdir() if path.is_dir())
            written = sorted(path.stem for path in output_dir.glob("*.md"))
            self.assertEqual(top_folders, written)

            for folder in top_folders:
                self.assertTrue((output_dir / f"{folder}.md").exists())

            certifications_text = (output_dir / "Certifications.md").read_text(encoding="utf-8")
            self.assertIn("ACS Grilamid LBV-50H FWA black 9225 18-12.pdf", certifications_text)

            competitors_text = (output_dir / "competitors.md").read_text(encoding="utf-8")
            self.assertIn("Competitor Price from Monthly Report_I&C.xlsx", competitors_text)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("summary", report)
            self.assertEqual(len(top_folders), report["summary"]["total_markdown_files"])
            self.assertIn("failed_files", report)


class ExportMarkdownCliBehaviorTests(unittest.TestCase):
    def _run_cli(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "myMAT_app.parser.export_markdown", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_non_strict_returns_zero_with_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            (kb / "Folder").mkdir(parents=True)
            (kb / "Folder" / "broken.pdf").write_text("not a real pdf", encoding="utf-8")
            output_dir = Path(tmp) / "markdown"
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                [
                    "--knowledge-root",
                    str(kb),
                    "--output-dir",
                    str(output_dir),
                    "--report-path",
                    str(report_path),
                ],
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue((output_dir / "Folder.md").exists())
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(report["summary"]["total_failures"], 1)

    def test_cli_strict_returns_one_with_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            (kb / "Folder").mkdir(parents=True)
            (kb / "Folder" / "broken.pdf").write_text("not a real pdf", encoding="utf-8")
            output_dir = Path(tmp) / "markdown"
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                [
                    "--knowledge-root",
                    str(kb),
                    "--output-dir",
                    str(output_dir),
                    "--report-path",
                    str(report_path),
                    "--strict",
                ],
                cwd=REPO_ROOT,
            )

            self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue(report_path.exists())

    def test_cli_missing_root_returns_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            output_dir = Path(tmp) / "markdown"
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                [
                    "--knowledge-root",
                    str(missing),
                    "--output-dir",
                    str(output_dir),
                    "--report-path",
                    str(report_path),
                ],
                cwd=REPO_ROOT,
            )

            self.assertEqual(2, proc.returncode)
            self.assertIn("Validation error", proc.stdout)


if __name__ == "__main__":
    unittest.main()
