from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from myMAT_app.parser.parser_config import ParseConfig
from myMAT_app.parser.parsers import parse_knowledge_base
from myMAT_app.parser.reporting import write_parse_report


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_KNOWLEDGE_ROOT = REPO_ROOT / "myMAT_knowledge"


class ParserIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not REAL_KNOWLEDGE_ROOT.exists():
            self.skipTest(f"Knowledge root not found: {REAL_KNOWLEDGE_ROOT}")

    def test_parse_real_knowledge_base_attempts_all_supported_files(self) -> None:
        config = ParseConfig(knowledge_root=REAL_KNOWLEDGE_ROOT)
        documents, results = parse_knowledge_base(config)

        expected_files = sorted(
            str(path)
            for path in REAL_KNOWLEDGE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in config.supported_extensions
        )
        parsed_files = sorted(result.source_path for result in results)

        self.assertEqual(len(expected_files), len(results))
        self.assertEqual(expected_files, parsed_files)
        self.assertGreater(len(documents), 0)

    def test_known_problematic_pdf_is_handled_with_actionable_state(self) -> None:
        config = ParseConfig(knowledge_root=REAL_KNOWLEDGE_ROOT)
        _, results = parse_knowledge_base(config)

        target_name = "ACS Grilamid LBV-50H FWA black 9225 18-12.pdf"
        target = None
        for result in results:
            if Path(result.source_path).name == target_name:
                target = result
                break

        self.assertIsNotNone(target, "Expected known problematic PDF in parse results")
        issue_codes = {issue.code for issue in target.issues}
        if target.status == "success":
            self.assertEqual("rapidocr_onnxruntime", target.parser_used)
            self.assertGreater(target.extracted_chars, 0)
            self.assertIn("pdf_ocr_applied", issue_codes)
        else:
            self.assertIn(target.status, {"warning", "failed"})
            self.assertIn("pdf_possible_scan_or_image_only", issue_codes)
            self.assertTrue(
                any(
                    "ocrmypdf" in issue.suggested_action.lower()
                    or "document ai" in issue.suggested_action.lower()
                    for issue in target.issues
                )
            )

    def test_report_json_schema(self) -> None:
        config = ParseConfig(knowledge_root=REAL_KNOWLEDGE_ROOT)
        _, results = parse_knowledge_base(config)

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "parse_report.json"
            write_parse_report(results, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertIn("generated_at", report)
        self.assertIn("summary", report)
        self.assertIn("files", report)
        self.assertIn("total_files", report["summary"])
        self.assertIn("extensions", report["summary"])
        self.assertIn("statuses", report["summary"])
        self.assertEqual(len(results), len(report["files"]))


class ParserCliTests(unittest.TestCase):
    def _run_cli(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "myMAT_app.parser.audit", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_non_strict_returns_zero_with_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            kb.mkdir(parents=True)
            (kb / "broken.pdf").write_text("not a real pdf", encoding="utf-8")
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                ["--knowledge-root", str(kb), "--report-path", str(report_path)],
                cwd=REPO_ROOT,
            )

            self.assertEqual(0, proc.returncode)
            self.assertTrue(report_path.exists())
            self.assertIn("Parser Audit Summary", proc.stdout)

    def test_cli_strict_returns_one_when_failures_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            kb.mkdir(parents=True)
            (kb / "broken.pdf").write_text("still not a real pdf", encoding="utf-8")
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                [
                    "--knowledge-root",
                    str(kb),
                    "--report-path",
                    str(report_path),
                    "--strict",
                ],
                cwd=REPO_ROOT,
            )

            self.assertEqual(1, proc.returncode)
            self.assertTrue(report_path.exists())

    def test_cli_missing_root_is_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist"
            report_path = Path(tmp) / "report.json"

            proc = self._run_cli(
                ["--knowledge-root", str(missing), "--report-path", str(report_path)],
                cwd=REPO_ROOT,
            )

            self.assertEqual(2, proc.returncode)
            self.assertIn("Validation error", proc.stdout)


if __name__ == "__main__":
    unittest.main()
