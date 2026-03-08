from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

from myMAT_app.parser.export_markdown import MarkdownExportConfig, export_folder_markdown
from myMAT_app.parser.parser_types import FileParseResult, ParseIssue


def _doc(
    *,
    source: str,
    source_name: str,
    doc_type: str,
    text: str,
    page_number: int | None = None,
    sheet_name: str | None = None,
) -> Document:
    metadata = {
        "source": source,
        "source_name": source_name,
        "source_ext": Path(source).suffix.lower(),
        "doc_type": doc_type,
        "parser_used": "PyPDFLoader",
        "fallback_used": False,
        "parse_status": "success",
        "extracted_chars": len(text),
    }
    if page_number is not None:
        metadata["page_number"] = page_number
    if sheet_name is not None:
        metadata["sheet_name"] = sheet_name
    return Document(page_content=text, metadata=metadata)


class ExportMarkdownUnitTests(unittest.TestCase):
    def test_folder_mapping_and_empty_folder_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            (root / "FolderA").mkdir(parents=True)
            (root / "FolderB").mkdir(parents=True)
            out_dir = Path(tmp) / "markdown"

            docs = [
                _doc(
                    source=str(root / "FolderA" / "file1.pdf"),
                    source_name="file1.pdf",
                    doc_type="FolderA",
                    text="content a",
                    page_number=1,
                )
            ]
            results = [
                FileParseResult(
                    source_path=str(root / "FolderA" / "file1.pdf"),
                    extension=".pdf",
                    status="success",
                    parser_used="PyPDFLoader",
                    fallback_used=False,
                    extracted_chars=9,
                    documents_count=1,
                    issues=[],
                )
            ]

            config = MarkdownExportConfig(knowledge_root=root, output_dir=out_dir)
            with patch(
                "myMAT_app.parser.export_markdown.parse_knowledge_base",
                return_value=(docs, results),
            ):
                run_result, _ = export_folder_markdown(config)

            self.assertEqual(2, run_result.total_markdown_files)
            self.assertTrue((out_dir / "FolderA.md").exists())
            self.assertTrue((out_dir / "FolderB.md").exists())
            folder_b_text = (out_dir / "FolderB.md").read_text(encoding="utf-8")
            self.assertIn("No parsed content found for this folder.", folder_b_text)

    def test_source_grouping_single_section_for_multi_segment_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            (root / "Visit_reports").mkdir(parents=True)
            out_dir = Path(tmp) / "markdown"
            source = str(root / "Visit_reports" / "report.pdf")

            docs = [
                _doc(
                    source=source,
                    source_name="report.pdf",
                    doc_type="Visit_reports",
                    text="page 2",
                    page_number=2,
                ),
                _doc(
                    source=source,
                    source_name="report.pdf",
                    doc_type="Visit_reports",
                    text="page 1",
                    page_number=1,
                ),
            ]
            results = [
                FileParseResult(
                    source_path=source,
                    extension=".pdf",
                    status="success",
                    parser_used="PyPDFLoader",
                    fallback_used=False,
                    extracted_chars=12,
                    documents_count=2,
                    issues=[],
                )
            ]

            config = MarkdownExportConfig(knowledge_root=root, output_dir=out_dir)
            with patch(
                "myMAT_app.parser.export_markdown.parse_knowledge_base",
                return_value=(docs, results),
            ):
                export_folder_markdown(config)

            text = (out_dir / "Visit_reports.md").read_text(encoding="utf-8")
            self.assertEqual(1, text.count("## Source: report.pdf"))
            self.assertIn("### Segment 1", text)
            self.assertIn("### Segment 2", text)

    def test_segment_order_is_page_then_sheet_then_insertion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            (root / "competitors").mkdir(parents=True)
            out_dir = Path(tmp) / "markdown"
            source = str(root / "competitors" / "sheet.xlsx")

            docs = [
                _doc(
                    source=source,
                    source_name="sheet.xlsx",
                    doc_type="competitors",
                    text="P2-Z",
                    page_number=2,
                    sheet_name="Zeta",
                ),
                _doc(
                    source=source,
                    source_name="sheet.xlsx",
                    doc_type="competitors",
                    text="P1",
                    page_number=1,
                ),
                _doc(
                    source=source,
                    source_name="sheet.xlsx",
                    doc_type="competitors",
                    text="P2-A",
                    page_number=2,
                    sheet_name="Alpha",
                ),
            ]
            results = [
                FileParseResult(
                    source_path=source,
                    extension=".xlsx",
                    status="success",
                    parser_used="openpyxl",
                    fallback_used=False,
                    extracted_chars=15,
                    documents_count=3,
                    issues=[],
                )
            ]

            config = MarkdownExportConfig(knowledge_root=root, output_dir=out_dir)
            with patch(
                "myMAT_app.parser.export_markdown.parse_knowledge_base",
                return_value=(docs, results),
            ):
                export_folder_markdown(config)

            text = (out_dir / "competitors.md").read_text(encoding="utf-8")
            idx_p1 = text.find("P1")
            idx_p2a = text.find("P2-A")
            idx_p2z = text.find("P2-Z")
            self.assertTrue(idx_p1 < idx_p2a < idx_p2z)

    def test_failed_files_are_rendered_with_actionable_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            (root / "Certifications").mkdir(parents=True)
            out_dir = Path(tmp) / "markdown"
            failed_source = str(root / "Certifications" / "broken.pdf")

            config = MarkdownExportConfig(knowledge_root=root, output_dir=out_dir)
            docs: list[Document] = []
            results = [
                FileParseResult(
                    source_path=failed_source,
                    extension=".pdf",
                    status="failed",
                    parser_used="PyPDFLoader",
                    fallback_used=True,
                    extracted_chars=0,
                    documents_count=0,
                    issues=[
                        ParseIssue(
                            severity="error",
                            code="pdf_possible_scan_or_image_only",
                            message="No extractable text from PDF.",
                            suggested_action="Use OCR with ocrmypdf.",
                        )
                    ],
                )
            ]

            with patch(
                "myMAT_app.parser.export_markdown.parse_knowledge_base",
                return_value=(docs, results),
            ):
                run_result, _ = export_folder_markdown(config)

            self.assertEqual(1, run_result.total_failures)
            text = (out_dir / "Certifications.md").read_text(encoding="utf-8")
            self.assertIn("## Parse Failures", text)
            self.assertIn("pdf_possible_scan_or_image_only", text)
            self.assertIn("Use OCR with ocrmypdf.", text)

    def test_special_characters_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge"
            (root / "A & B").mkdir(parents=True)
            out_dir = Path(tmp) / "markdown"
            source_name = "2025-12-05_XUBI_Moons'.docx"
            source_path = str(root / "A & B" / source_name)

            docs = [
                _doc(
                    source=source_path,
                    source_name=source_name,
                    doc_type="A & B",
                    text="special chars",
                )
            ]
            results = [
                FileParseResult(
                    source_path=source_path,
                    extension=".docx",
                    status="success",
                    parser_used="Docx2txtLoader",
                    fallback_used=False,
                    extracted_chars=13,
                    documents_count=1,
                    issues=[],
                )
            ]

            config = MarkdownExportConfig(knowledge_root=root, output_dir=out_dir)
            with patch(
                "myMAT_app.parser.export_markdown.parse_knowledge_base",
                return_value=(docs, results),
            ):
                export_folder_markdown(config)

            md_path = out_dir / "A & B.md"
            self.assertTrue(md_path.exists())
            text = md_path.read_text(encoding="utf-8")
            self.assertIn(source_name, text)


if __name__ == "__main__":
    unittest.main()
