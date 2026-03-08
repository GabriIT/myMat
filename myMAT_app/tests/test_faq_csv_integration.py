from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from myMAT_app.faq.generate_csv import main


def _write_markdown(path: Path, source_name: str, text: str) -> None:
    content = f"""
# Folder

## Source: {source_name}
- source_path: /tmp/{source_name}

### Segment 1
{text}

## Parse Failures
No failed files for this folder.
""".strip()
    path.write_text(content, encoding="utf-8")


class FAQCsvIntegrationTests(unittest.TestCase):
    def test_generation_with_mocked_llm_creates_valid_csv_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "markdown"
            input_dir.mkdir(parents=True)
            _write_markdown(
                input_dir / "Technical_sheets.md",
                "alpha.pdf",
                "Grilamid provides high dimensional stability and chemical resistance.",
            )
            _write_markdown(
                input_dir / "Projects.md",
                "beta.pdf",
                "Project roadmap includes tooling updates and qualification phases.",
            )

            output_csv = tmp_path / "faq.csv"
            report_path = tmp_path / "report.json"
            templates = [
                "What material property is described for {marker} in {file}?",
                "Which process step is highlighted for {marker} in {file}?",
                "What compliance detail is stated for {marker} in {file}?",
                "Which performance indicator appears for {marker} in {file}?",
                "What project status note is given for {marker} in {file}?",
                "Which quality requirement is listed for {marker} in {file}?",
                "What operational constraint is documented for {marker} in {file}?",
                "Which application context is explained for {marker} in {file}?",
                "What technical recommendation is provided for {marker} in {file}?",
                "Which validation result is reported for {marker} in {file}?",
            ]

            def fake_candidates(_llm, chunk, target_count, max_retries, generation_mode):
                items = []
                for idx in range(target_count):
                    marker = f"{chunk.source_name.replace('.', ' ')} item {chunk.chunk_index}-{idx}"
                    template = templates[idx % len(templates)]
                    category = chunk.markdown_filename.replace(".md", "")
                    if generation_mode == "classification":
                        answer = (
                            f"Category: {category}. "
                            f"The source states documented details for {marker} with "
                            "explicit factual wording."
                        )
                    else:
                        answer = (
                            f"The source states documented details for {marker} with "
                            "explicit factual wording."
                        )
                    items.append(
                        {
                            "question": template.format(
                                marker=marker, file=chunk.markdown_filename
                            ),
                            "answer": answer,
                        }
                    )
                return items

            with patch(
                "myMAT_app.faq.generate_csv._generate_candidates_for_chunk",
                side_effect=fake_candidates,
            ):
                code = main(
                    [
                        "--input-dir",
                        str(input_dir),
                        "--output-csv",
                        str(output_csv),
                        "--report-path",
                        str(report_path),
                        "--min-rows",
                        "20",
                        "--max-rows",
                        "35",
                    ]
                )

            self.assertEqual(0, code)
            self.assertTrue(output_csv.exists())
            self.assertTrue(report_path.exists())

            with output_csv.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(["Index", "Question", "Answer", "source"], reader.fieldnames)
                rows = list(reader)
            self.assertGreaterEqual(len(rows), 20)
            self.assertLessEqual(len(rows), 35)
            self.assertTrue(all("::" in row["source"] for row in rows))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("summary", report)
            self.assertGreaterEqual(report["summary"]["rows_written"], 20)

    def test_classification_mode_enforces_category_style_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "markdown"
            input_dir.mkdir(parents=True)
            _write_markdown(
                input_dir / "Certifications.md",
                "alpha.pdf",
                "Certificate confirms migration test status and expiry date.",
            )
            output_csv = tmp_path / "faq.csv"
            report_path = tmp_path / "report.json"

            def fake_candidates(_llm, _chunk, target_count, max_retries, generation_mode):
                return [
                    {
                        "question": f"Which standard is mentioned in the certificate item {idx}?",
                        "answer": "The document cites XP P 41-250 for migration tests.",
                    }
                    for idx in range(target_count)
                ]

            with patch(
                "myMAT_app.faq.generate_csv._generate_candidates_for_chunk",
                side_effect=fake_candidates,
            ):
                code = main(
                    [
                        "--input-dir",
                        str(input_dir),
                        "--output-csv",
                        str(output_csv),
                        "--report-path",
                        str(report_path),
                        "--generation-mode",
                        "classification",
                        "--min-rows",
                        "8",
                        "--max-rows",
                        "20",
                    ]
                )

            self.assertEqual(0, code)
            with output_csv.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(
                all(
                    row["Question"].startswith(
                        "Which category should this document be classified under based on:"
                    )
                    for row in rows
                )
            )
            self.assertTrue(
                all(row["Answer"].startswith("Category: Certifications.") for row in rows)
            )

    def test_cli_strict_returns_one_when_row_target_not_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "markdown"
            input_dir.mkdir(parents=True)
            _write_markdown(input_dir / "Certifications.md", "gamma.pdf", "Certification details.")

            with patch(
                "myMAT_app.faq.generate_csv._generate_candidates_for_chunk",
                return_value=[],
            ):
                code = main(
                    [
                        "--input-dir",
                        str(input_dir),
                        "--output-csv",
                        str(tmp_path / "faq.csv"),
                        "--report-path",
                        str(tmp_path / "report.json"),
                        "--min-rows",
                        "10",
                        "--strict",
                    ]
                )
            self.assertEqual(1, code)

    def test_cli_missing_input_dir_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing_dir = tmp_path / "missing"
            code = main(
                [
                    "--input-dir",
                    str(missing_dir),
                    "--output-csv",
                    str(tmp_path / "faq.csv"),
                ]
            )
            self.assertEqual(2, code)

    def test_cli_empty_markdown_directory_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "empty"
            input_dir.mkdir(parents=True)
            code = main(
                [
                    "--input-dir",
                    str(input_dir),
                    "--output-csv",
                    str(tmp_path / "faq.csv"),
                ]
            )
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
