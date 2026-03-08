from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_minimal_docx(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        + text
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml)


class IncrementalSourcePipelineTests(unittest.TestCase):
    def test_pipeline_processes_new_files_then_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            knowledge_root = tmp_root / "kb"
            markdown_dir = tmp_root / "md_out"
            chunks_path = tmp_root / "chunks.jsonl"
            state_path = tmp_root / "state.json"
            report_path = tmp_root / "report.json"

            _make_minimal_docx(knowledge_root / "Visit_reports" / "demo.docx", "incremental test")

            cmd = [
                sys.executable,
                "-m",
                "myMAT_app.parser.incremental_source_pipeline",
                "--knowledge-root",
                str(knowledge_root),
                "--markdown-output-dir",
                str(markdown_dir),
                "--chunks-output-path",
                str(chunks_path),
                "--state-path",
                str(state_path),
                "--report-path",
                str(report_path),
            ]

            first = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertTrue(chunks_path.exists())
            self.assertTrue(state_path.exists())
            self.assertTrue(report_path.exists())

            first_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(1, first_report["selection"]["selected_files_count"])
            self.assertGreaterEqual(first_report["parse"]["documents_count"], 1)

            second = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            second_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(0, second_report["selection"]["selected_files_count"])


if __name__ == "__main__":
    unittest.main()
