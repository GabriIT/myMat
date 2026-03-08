from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

from myMAT_app.parser.parser_config import ParseConfig
from myMAT_app.parser.parser_types import FileParseResult, ParseIssue
from myMAT_app.parser.parsers import parse_docx_file, parse_knowledge_base
from myMAT_app.parser.reporting import build_parse_report


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


class ParserUnitTests(unittest.TestCase):
    def test_dispatch_routes_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kb").mkdir(parents=True)
            (root / "kb" / "a.pdf").write_bytes(b"%PDF-1.4")
            _make_minimal_docx(root / "kb" / "b.docx", "docx text")
            (root / "kb" / "c.xlsx").write_bytes(b"PK")
            (root / "kb" / "d.pptx").write_bytes(b"PK")
            (root / "kb" / "ignore.txt").write_text("ignored", encoding="utf-8")

            config = ParseConfig(knowledge_root=root)

            def _fake(ext: str):
                def _runner(path: Path, _config: ParseConfig):
                    doc = Document(page_content="content", metadata={"source": str(path)})
                    result = FileParseResult(
                        source_path=str(path),
                        extension=ext,
                        status="success",
                        parser_used=f"{ext}_parser",
                        fallback_used=False,
                        extracted_chars=7,
                        documents_count=1,
                        issues=[],
                    )
                    return [doc], result

                return _runner

            with (
                patch("myMAT_app.parser.parsers.parse_pdf_file", side_effect=_fake(".pdf")) as m_pdf,
                patch("myMAT_app.parser.parsers.parse_docx_file", side_effect=_fake(".docx")) as m_docx,
                patch("myMAT_app.parser.parsers.parse_xlsx_file", side_effect=_fake(".xlsx")) as m_xlsx,
                patch("myMAT_app.parser.parsers.parse_pptx_file", side_effect=_fake(".pptx")) as m_pptx,
            ):
                docs, results = parse_knowledge_base(config)

            self.assertEqual(1, m_pdf.call_count)
            self.assertEqual(1, m_docx.call_count)
            self.assertEqual(1, m_xlsx.call_count)
            self.assertEqual(1, m_pptx.call_count)
            self.assertEqual(4, len(results))
            self.assertEqual(4, len(docs))
            self.assertEqual({".pdf", ".docx", ".xlsx", ".pptx"}, {result.extension for result in results})

    def test_docx_thresholds_trigger_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Visit_reports" / "short.docx"
            _make_minimal_docx(path, "short")

            strict_config = ParseConfig(knowledge_root=root, min_chars_docx=100)
            _, strict_result = parse_docx_file(path, strict_config)
            self.assertEqual("warning", strict_result.status)

            relaxed_config = ParseConfig(knowledge_root=root, min_chars_docx=1)
            docs, relaxed_result = parse_docx_file(path, relaxed_config)
            self.assertEqual("success", relaxed_result.status)
            self.assertGreaterEqual(len(docs), 1)

    def test_report_aggregation(self) -> None:
        results = [
            FileParseResult(
                source_path="/tmp/a.pdf",
                extension=".pdf",
                status="success",
                parser_used="p",
                fallback_used=False,
                extracted_chars=100,
                documents_count=2,
                issues=[],
            ),
            FileParseResult(
                source_path="/tmp/b.docx",
                extension=".docx",
                status="warning",
                parser_used="d",
                fallback_used=True,
                extracted_chars=10,
                documents_count=1,
                issues=[
                    ParseIssue(
                        severity="warning",
                        code="docx_low_text",
                        message="low",
                        suggested_action="retry",
                    )
                ],
            ),
            FileParseResult(
                source_path="/tmp/c.xlsx",
                extension=".xlsx",
                status="failed",
                parser_used="x",
                fallback_used=True,
                extracted_chars=0,
                documents_count=0,
                issues=[
                    ParseIssue(
                        severity="error",
                        code="xlsx_no_extractable_cells",
                        message="none",
                        suggested_action="convert",
                    )
                ],
            ),
        ]
        report = build_parse_report(results)
        self.assertEqual(3, report["summary"]["total_files"])
        self.assertEqual(3, report["summary"]["total_documents"])
        self.assertEqual(1, report["summary"]["extensions"][".pdf"])
        self.assertEqual(1, report["summary"]["statuses"]["failed"])
        self.assertEqual(1, report["summary"]["issue_codes"]["docx_low_text"])

    def test_special_char_filename_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            special = root / "Visit_reports" / "2025-12-05_XUBI_Moons'.docx"
            _make_minimal_docx(special, "Document with special filename")

            config = ParseConfig(knowledge_root=root, min_chars_docx=5)
            docs, result = parse_docx_file(special, config)

            self.assertEqual(str(special), result.source_path)
            self.assertEqual(special.name, docs[0].metadata["source_name"])
            self.assertEqual(str(special), docs[0].metadata["source"])

    def test_include_paths_processes_only_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kb").mkdir(parents=True)
            selected = root / "kb" / "keep.pdf"
            ignored = root / "kb" / "skip.docx"
            selected.write_bytes(b"%PDF-1.4")
            _make_minimal_docx(ignored, "ignore me")

            config = ParseConfig(knowledge_root=root, include_paths=[selected])

            def _fake_pdf(path: Path, _config: ParseConfig):
                doc = Document(page_content="ok", metadata={"source": str(path)})
                result = FileParseResult(
                    source_path=str(path),
                    extension=".pdf",
                    status="success",
                    parser_used="pdf_parser",
                    fallback_used=False,
                    extracted_chars=2,
                    documents_count=1,
                    issues=[],
                )
                return [doc], result

            with (
                patch("myMAT_app.parser.parsers.parse_pdf_file", side_effect=_fake_pdf) as m_pdf,
                patch("myMAT_app.parser.parsers.parse_docx_file") as m_docx,
            ):
                docs, results = parse_knowledge_base(config)

            self.assertEqual(1, m_pdf.call_count)
            self.assertEqual(0, m_docx.call_count)
            self.assertEqual(1, len(docs))
            self.assertEqual(1, len(results))
            self.assertEqual(str(selected), results[0].source_path)


if __name__ == "__main__":
    unittest.main()
