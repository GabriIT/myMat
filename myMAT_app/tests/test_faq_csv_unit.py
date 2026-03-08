from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from myMAT_app.faq.generate_csv import (
    FAQRow,
    _augment_rows_for_classification,
    _dedupe_and_validate,
    _is_valid_row,
    _sort_and_index_rows,
    _source_value,
    _trim_rows_balanced,
    _write_csv,
    parse_markdown_source_sections,
)


class FAQCsvUnitTests(unittest.TestCase):
    def test_parse_markdown_source_sections_extracts_source_blocks(self) -> None:
        markdown = """
# Folder

## Source: alpha.pdf
- source_path: /tmp/alpha.pdf

### Segment 1
Alpha content line one.

### Segment 2
Alpha content line two.

## Source: beta.docx
### Segment 1
Beta content.

## Parse Failures
### broken.pdf
- [pdf_error] failed
""".strip()
        units = parse_markdown_source_sections(markdown, "Folder.md")
        self.assertEqual(2, len(units))
        self.assertEqual("alpha.pdf", units[0].source_name)
        self.assertIn("Alpha content line one.", units[0].content)
        self.assertEqual("beta.docx", units[1].source_name)
        self.assertIn("Beta content.", units[1].content)
        self.assertEqual("Folder.md", units[0].markdown_filename)

    def test_row_validator_rejects_low_signal_rows(self) -> None:
        self.assertFalse(_is_valid_row("Q", "This is a long answer but short question", "s"))
        self.assertFalse(_is_valid_row("What is this?", "I do not know.", "s"))
        self.assertFalse(_is_valid_row("What is this?", "Too short", "s"))
        self.assertFalse(
            _is_valid_row(
                "State the certification detail tied to key 793ad264f753d6db?",
                "Entry 793ad264f753d6db is grounded in the corresponding markdown segment.",
                "monthly_reports.md::report.pdf",
            )
        )
        self.assertTrue(
            _is_valid_row(
                "What is Grilamid used for?",
                "It is used in engineering components requiring stiffness and stability.",
                "Technical_sheets.md::x.pdf",
            )
        )

    def test_dedupe_removes_exact_and_near_duplicate_questions(self) -> None:
        rows = [
            FAQRow(
                index=0,
                question="What is Grilamid material?",
                answer="Grilamid is a polyamide used in engineering applications.",
                source="a.md::x.pdf",
            ),
            FAQRow(
                index=0,
                question="What is Grilamid material?",
                answer="Grilamid material is referenced as a high-performance engineering polymer.",
                source="a.md::x.pdf",
            ),
            FAQRow(
                index=0,
                question="What is Grilamid materials?",
                answer="It is a family of engineering polymers referenced in this same source.",
                source="a.md::x.pdf",
            ),
        ]
        deduped, duplicates_removed, invalid_removed = _dedupe_and_validate(rows)
        self.assertEqual(1, len(deduped))
        self.assertEqual(2, duplicates_removed)
        self.assertEqual(0, invalid_removed)

    def test_source_formatter(self) -> None:
        self.assertEqual(
            "Technical_sheets.md::HT1V-3 FWA_black 9225_EN.pdf",
            _source_value("Technical_sheets.md", "HT1V-3 FWA_black 9225_EN.pdf"),
        )

    def test_csv_writer_outputs_required_header_and_indices(self) -> None:
        rows = [
            FAQRow(
                index=0,
                question="b question",
                answer="This is a sufficiently long answer for question b.",
                source="B.md::b.pdf",
            ),
            FAQRow(
                index=0,
                question="a question",
                answer="This is a sufficiently long answer for question a.",
                source="A.md::a.pdf",
            ),
        ]
        ordered = _sort_and_index_rows(rows)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "faq.csv"
            _write_csv(ordered, out)
            self.assertTrue(out.exists())
            with out.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(["Index", "Question", "Answer", "source"], reader.fieldnames)
                records = list(reader)
            self.assertEqual("1", records[0]["Index"])
            self.assertEqual("2", records[1]["Index"])
            self.assertEqual("A.md::a.pdf", records[0]["source"])

    def test_balanced_trim_keeps_multiple_sources(self) -> None:
        rows: list[FAQRow] = []
        for idx in range(6):
            rows.append(
                FAQRow(
                    index=0,
                    question=f"Q A {idx}?",
                    answer="Category: A. A sufficiently long answer for source A.",
                    source="A.md::a.pdf",
                )
            )
        for idx in range(2):
            rows.append(
                FAQRow(
                    index=0,
                    question=f"Q B {idx}?",
                    answer="Category: B. A sufficiently long answer for source B.",
                    source="B.md::b.pdf",
                )
            )

        trimmed = _trim_rows_balanced(rows, 4)
        sources = [row.source for row in trimmed]
        self.assertEqual(4, len(trimmed))
        self.assertIn("A.md::a.pdf", sources)
        self.assertIn("B.md::b.pdf", sources)

    def test_classification_augmentation_expands_rows(self) -> None:
        base = [
            FAQRow(
                index=0,
                question="What is the expiration date of the ACS certificate?",
                answer="Category: Certifications. The certificate expires on 12 February 2026.",
                source="Certifications.md::file.pdf",
            ),
            FAQRow(
                index=0,
                question="Which standards were used for migration tests?",
                answer="Category: Certifications. Migration tests followed XP P 41-250 standards.",
                source="Certifications.md::file.pdf",
            ),
        ]
        augmented = _augment_rows_for_classification(base, 6)
        self.assertGreaterEqual(len(augmented), 6)
        self.assertTrue(
            any(
                row.question.startswith(
                    "Which category should this document be classified under based on:"
                )
                for row in augmented
            )
        )


if __name__ == "__main__":
    unittest.main()
