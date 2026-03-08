from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from myMAT_app.parser.parser_config import ParseConfig
from myMAT_app.parser.parsers import parse_pptx_file


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PPTX = (
    REPO_ROOT / "myMAT_knowledge" / "Metal_Replacement" / "202401 - Metal Replacement.pptx"
)


class PptxParserIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        if not REFERENCE_PPTX.exists():
            self.skipTest(f"Reference PPTX not found: {REFERENCE_PPTX}")

    def test_reference_pptx_parses_with_slide_documents(self) -> None:
        config = ParseConfig(
            knowledge_root=REFERENCE_PPTX.parent,
            min_chars_pptx=1,
            min_chars_pptx_slide=1,
        )
        docs, result = parse_pptx_file(REFERENCE_PPTX, config)

        self.assertGreater(len(docs), 0)
        self.assertEqual(".pptx", result.extension)
        self.assertIn(result.status, {"success", "warning"})

        slide_numbers = sorted(
            {
                int(doc.metadata.get("slide_number"))
                for doc in docs
                if doc.metadata.get("slide_number") is not None
            }
        )
        self.assertGreaterEqual(len(slide_numbers), 20)
        self.assertEqual(1, slide_numbers[0])


class PptxProbeCliTests(unittest.TestCase):
    def _run_probe(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "myMAT_app.parser.pptx_probe", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_probe_missing_path_returns_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.pptx"
            report_path = Path(tmp) / "report.json"
            proc = self._run_probe(
                ["--pptx-path", str(missing), "--report-path", str(report_path)]
            )
            self.assertEqual(2, proc.returncode)
            self.assertIn("Validation error", proc.stdout)

    def test_probe_reference_file_outputs_json_report(self) -> None:
        if not REFERENCE_PPTX.exists():
            self.skipTest(f"Reference PPTX not found: {REFERENCE_PPTX}")

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "pptx_probe_report.json"
            proc = self._run_probe(
                [
                    "--pptx-path",
                    str(REFERENCE_PPTX),
                    "--report-path",
                    str(report_path),
                ]
            )

            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("result", report)
            self.assertIn("documents", report)
            self.assertGreater(report["documents"]["count"], 0)


class PptxStrictAuditBehaviorTests(unittest.TestCase):
    def test_audit_strict_returns_one_for_broken_pptx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            kb.mkdir(parents=True)
            (kb / "broken.pptx").write_bytes(b"not a valid pptx")
            report_path = Path(tmp) / "audit_report.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "myMAT_app.parser.audit",
                    "--knowledge-root",
                    str(kb),
                    "--report-path",
                    str(report_path),
                    "--strict",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
