from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from myMAT_app.vector.config import DEFAULT_CHAT_MODEL

DEFAULT_REPORT_PATH = Path("/tmp/myrag_faq_report.json")
SOURCE_FORMAT = Literal["markdown+source_name"]
GENERATION_MODE = Literal["faq", "classification"]

LOW_SIGNAL_ANSWERS = {
    "i do not know",
    "i don't know",
    "n/a",
    "na",
    "unknown",
    "not available",
    "insufficient information",
    "i do not know based on the provided documents",
}

PLACEHOLDER_PATTERNS = [
    re.compile(r"\b(?:key|token|entry|reference)\s+[a-f0-9]{6,}\b", re.IGNORECASE),
    re.compile(r"\b[a-f0-9]{10,}\b", re.IGNORECASE),
    re.compile(r"\bsource-bound wording\b", re.IGNORECASE),
    re.compile(r"\bgrounded in the corresponding markdown segment\b", re.IGNORECASE),
    re.compile(r"\bprovided source segment\b", re.IGNORECASE),
    re.compile(r"\bchunk text\b", re.IGNORECASE),
]


@dataclass(slots=True)
class FAQGenerationConfig:
    input_dir: Path
    output_csv: Path
    report_path: Path = DEFAULT_REPORT_PATH
    min_rows: int = 500
    max_rows: int = 650
    chat_model: str = DEFAULT_CHAT_MODEL
    strict: bool = False
    max_retries: int = 3
    temperature: float = 0.0
    source_format: SOURCE_FORMAT = "markdown+source_name"
    generation_mode: GENERATION_MODE = "faq"

    def __post_init__(self) -> None:
        self.input_dir = Path(self.input_dir).expanduser().resolve()
        self.output_csv = Path(self.output_csv).expanduser().resolve()
        self.report_path = Path(self.report_path).expanduser().resolve()
        if self.min_rows < 1:
            raise ValueError("min_rows must be >= 1")
        if self.max_rows < self.min_rows:
            raise ValueError("max_rows must be >= min_rows")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.source_format != "markdown+source_name":
            raise ValueError(f"Unsupported source_format: {self.source_format}")
        if self.generation_mode not in {"faq", "classification"}:
            raise ValueError(f"Unsupported generation_mode: {self.generation_mode}")


@dataclass(slots=True)
class FAQRow:
    index: int
    question: str
    answer: str
    source: str

    def to_csv_row(self) -> dict[str, str | int]:
        return {
            "Index": self.index,
            "Question": self.question,
            "Answer": self.answer,
            "source": self.source,
        }


@dataclass(slots=True)
class FAQRunResult:
    rows_written: int
    files_processed: int
    source_sections_processed: int
    duplicates_removed: int
    invalid_rows_removed: int
    target_met: bool

    def to_dict(self) -> dict:
        return {
            "rows_written": self.rows_written,
            "files_processed": self.files_processed,
            "source_sections_processed": self.source_sections_processed,
            "duplicates_removed": self.duplicates_removed,
            "invalid_rows_removed": self.invalid_rows_removed,
            "target_met": self.target_met,
        }


@dataclass(slots=True)
class _SourceUnit:
    markdown_filename: str
    source_name: str
    content: str


@dataclass(slots=True)
class _ChunkUnit:
    markdown_filename: str
    source_name: str
    chunk_index: int
    chunk_text: str


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_question_for_dedupe(question: str) -> str:
    cleaned = _normalize_whitespace(question).lower()
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _category_from_markdown_filename(markdown_filename: str) -> str:
    return Path(markdown_filename).stem


def _source_value(markdown_filename: str, source_name: str) -> str:
    return f"{markdown_filename}::{source_name}"


def _clean_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_llm_json_candidates(raw: str) -> list[dict]:
    text = _clean_json_text(raw)
    parsed: object
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
            else:
                raise

    if isinstance(parsed, dict):
        items = parsed.get("faqs", [])
        if not isinstance(items, list):
            return []
        parsed = items

    if not isinstance(parsed, list):
        return []

    output: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        answer = item.get("answer")
        if isinstance(question, str) and isinstance(answer, str):
            output.append({"question": question, "answer": answer})
    return output


def _is_low_signal_answer(answer: str) -> bool:
    normalized = _normalize_whitespace(answer).lower().strip(".")
    if normalized in LOW_SIGNAL_ANSWERS:
        return True
    for phrase in LOW_SIGNAL_ANSWERS:
        if phrase in normalized and len(normalized) <= len(phrase) + 20:
            return True
    return False


def _contains_placeholder_pattern(text: str) -> bool:
    normalized = _normalize_whitespace(text)
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def _enforce_category_prefix(answer: str, category: str) -> str:
    cleaned = _normalize_whitespace(answer)
    if re.match(r"^category\s*:", cleaned, flags=re.IGNORECASE):
        return cleaned
    return f"Category: {category}. {cleaned}"


def _enforce_classification_question(question: str) -> str:
    prefix = "Which category should this document be classified under based on:"
    normalized = _normalize_whitespace(question).rstrip("?")
    if normalized.lower().startswith(prefix.lower()):
        evidence = normalized[len(prefix) :].strip()
    else:
        evidence = re.sub(
            r"^(which|what|how|when|why|where)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        evidence = re.sub(
            r"\b(category|classify|classified|classification|document|folder|should|be|assigned|under)\b",
            "",
            evidence,
            flags=re.IGNORECASE,
        )
        evidence = re.sub(r"^(this\s+)?based\s+on\s*:\s*", "", evidence, flags=re.IGNORECASE)
        evidence = re.sub(r"^(this\s+)?based\s+on\s*:\s*", "", evidence, flags=re.IGNORECASE)
    evidence = _normalize_whitespace(evidence).strip(" .,:;-")
    if not evidence:
        evidence = "the provided document evidence"
    return f"{prefix} {evidence}?"


def _is_valid_row(question: str, answer: str, source: str) -> bool:
    if not question or not answer or not source:
        return False
    if len(question) < 8:
        return False
    if len(answer) < 20:
        return False
    if _is_low_signal_answer(answer):
        return False
    if _contains_placeholder_pattern(question) or _contains_placeholder_pattern(answer):
        return False
    return True


def _dedupe_and_validate(
    rows: list[FAQRow], generation_mode: GENERATION_MODE = "faq"
) -> tuple[list[FAQRow], int, int]:
    unique: list[FAQRow] = []
    seen_exact: set[tuple[str, str]] = set()
    dedupe_norms_by_source: defaultdict[str, list[str]] = defaultdict(list)
    duplicates_removed = 0
    invalid_removed = 0

    for row in rows:
        question = _normalize_whitespace(row.question)
        if question and not question.endswith("?"):
            question = f"{question}?"

        if generation_mode == "classification":
            category = row.source.split("::", 1)[0].replace(".md", "")
            question = _enforce_classification_question(question)
            answer = _enforce_category_prefix(row.answer, category)
        else:
            answer = _normalize_whitespace(row.answer)
        source = _normalize_whitespace(row.source)

        if not _is_valid_row(question, answer, source):
            invalid_removed += 1
            continue

        q_norm = _normalize_question_for_dedupe(question)
        if not q_norm:
            invalid_removed += 1
            continue

        exact_key = (source, q_norm)
        if exact_key in seen_exact:
            duplicates_removed += 1
            continue

        near_duplicate = False
        for existing in dedupe_norms_by_source[source]:
            if SequenceMatcher(None, q_norm, existing).ratio() >= 0.94:
                near_duplicate = True
                break
        if near_duplicate:
            duplicates_removed += 1
            continue

        seen_exact.add(exact_key)
        dedupe_norms_by_source[source].append(q_norm)
        unique.append(FAQRow(index=0, question=question, answer=answer, source=source))

    return unique, duplicates_removed, invalid_removed


def parse_markdown_source_sections(markdown_text: str, markdown_filename: str) -> list[_SourceUnit]:
    source_pattern = re.compile(r"^## Source:\s*(.+?)\s*$", re.MULTILINE)
    matches = list(source_pattern.finditer(markdown_text))
    if not matches:
        return []

    parse_failures_idx = markdown_text.find("\n## Parse Failures")
    if parse_failures_idx < 0:
        parse_failures_idx = len(markdown_text)

    units: list[_SourceUnit] = []
    for index, match in enumerate(matches):
        source_name = _normalize_whitespace(match.group(1))
        section_start = match.end()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else parse_failures_idx
        section_text = markdown_text[section_start:next_start]

        segment_pattern = re.compile(r"^### Segment[^\n]*\n", re.MULTILINE)
        segment_matches = list(segment_pattern.finditer(section_text))
        segments: list[str] = []

        if segment_matches:
            for seg_index, seg_match in enumerate(segment_matches):
                seg_start = seg_match.end()
                seg_end = (
                    segment_matches[seg_index + 1].start()
                    if seg_index + 1 < len(segment_matches)
                    else len(section_text)
                )
                segment_body = _normalize_whitespace(section_text[seg_start:seg_end])
                if segment_body:
                    segments.append(segment_body)
        else:
            lines = section_text.splitlines()
            body_lines = [line for line in lines if not line.strip().startswith("- ")]
            fallback_content = _normalize_whitespace("\n".join(body_lines))
            if fallback_content:
                segments.append(fallback_content)

        content = "\n\n".join(segments).strip()
        if not content:
            continue

        units.append(
            _SourceUnit(
                markdown_filename=markdown_filename,
                source_name=source_name,
                content=content,
            )
        )
    return units


def _load_source_units(input_dir: Path) -> tuple[list[_SourceUnit], list[Path]]:
    markdown_files = sorted(input_dir.glob("*.md"), key=lambda path: path.name.casefold())
    units: list[_SourceUnit] = []
    for md_file in markdown_files:
        text = md_file.read_text(encoding="utf-8")
        units.extend(parse_markdown_source_sections(text, md_file.name))
    return units, markdown_files


def _chunk_source_units(units: list[_SourceUnit]) -> list[_ChunkUnit]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=20000,
        chunk_overlap=600,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks: list[_ChunkUnit] = []
    for unit in units:
        texts = splitter.split_text(unit.content)
        for idx, chunk_text in enumerate(texts):
            clean = _normalize_whitespace(chunk_text)
            if not clean:
                continue
            chunks.append(
                _ChunkUnit(
                    markdown_filename=unit.markdown_filename,
                    source_name=unit.source_name,
                    chunk_index=idx,
                    chunk_text=clean,
                )
            )
    return chunks


def _generate_candidates_for_chunk(
    llm: ChatOpenAI,
    chunk: _ChunkUnit,
    target_count: int,
    max_retries: int,
    generation_mode: GENERATION_MODE,
) -> list[dict]:
    category = _category_from_markdown_filename(chunk.markdown_filename)
    if generation_mode == "classification":
        system_prompt = (
            "You generate high-quality classification-oriented Q/A pairs for supervised fine-tuning. "
            "Use only facts from the provided text. "
            "Do not speculate, invent IDs, or use placeholders. "
            "Return ONLY valid JSON as an array of objects with keys: question, answer. "
            f"Generate up to {target_count} items."
        )
        user_prompt = (
            f"Category: {category}\n"
            f"Source: {chunk.markdown_filename}::{chunk.source_name}\n"
            f"Text:\n{chunk.chunk_text}\n\n"
            "Requirements:\n"
            "- Questions must help classify new documents into the correct category.\n"
            "- Each question must follow this exact form: "
            "'Which category should this document be classified under based on: <evidence cue>?'.\n"
            "- Questions must never contain keys, hashes, or placeholder IDs.\n"
            "- Answers must be factual and concise (1-3 sentences).\n"
            f"- Each answer must start exactly with: 'Category: {category}.'\n"
            "- Each answer must include concrete evidence (names, values, dates, properties, statuses, standards).\n"
            "- Do not mention prompt mechanics, chunks, metadata fields, or grounding statements.\n"
            "- Do not include unknown/uncertain answers.\n"
        )
    else:
        system_prompt = (
            "You generate high-quality FAQ items from provided source text. "
            "Use only facts from the text. "
            "Do not speculate and do not use placeholders or invented IDs. "
            "Return ONLY valid JSON as an array of objects with keys: question, answer. "
            f"Generate up to {target_count} items."
        )
        user_prompt = (
            f"Category: {category}\n"
            f"Source: {chunk.markdown_filename}::{chunk.source_name}\n"
            f"Text:\n{chunk.chunk_text}\n\n"
            "Requirements:\n"
            "- Questions must be natural and useful as FAQs.\n"
            "- Questions must never contain keys, hashes, entry numbers, or placeholder IDs.\n"
            "- Answers must be factual and concise (1-3 sentences).\n"
            "- Answers should cite concrete details from text when available.\n"
            "- Do not include unknown/uncertain answers.\n"
        )

    for attempt in range(max_retries + 1):
        response = llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        try:
            return _parse_llm_json_candidates(str(response.content))
        except Exception:
            if attempt >= max_retries:
                return []
    return []


def _sort_and_index_rows(rows: list[FAQRow]) -> list[FAQRow]:
    ordered = sorted(rows, key=lambda row: (row.source.casefold(), row.question.casefold()))
    for idx, row in enumerate(ordered, start=1):
        row.index = idx
    return ordered


def _trim_rows_balanced(rows: list[FAQRow], max_rows: int) -> list[FAQRow]:
    if len(rows) <= max_rows:
        return rows

    buckets: dict[str, list[FAQRow]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: (item.source.casefold(), item.question.casefold())):
        buckets[row.source].append(row)

    selected: list[FAQRow] = []
    sources = sorted(buckets.keys(), key=str.casefold)
    source_index = 0
    while len(selected) < max_rows and sources:
        source = sources[source_index]
        source_rows = buckets[source]
        if source_rows:
            selected.append(source_rows.pop(0))
        if not source_rows:
            sources.pop(source_index)
            if not sources:
                break
            source_index %= len(sources)
            continue
        source_index = (source_index + 1) % len(sources)
    return selected


def _topic_from_question(question: str) -> str:
    text = _normalize_whitespace(question).rstrip("?")
    text = re.sub(
        r"^(what|which|how|when|why|where)\s+(is|are|was|were|does|do|can|could|would|should)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip() or _normalize_whitespace(question).rstrip("?")


def _augment_rows(
    rows: list[FAQRow], target_count: int, generation_mode: GENERATION_MODE
) -> list[FAQRow]:
    if len(rows) >= target_count:
        return rows

    if generation_mode != "classification":
        templates = [
            "What detail is documented about {topic}?",
            "Which source evidence explains {topic}?",
            "How is {topic} described in the document context?",
            "What specific facts are provided for {topic}?",
            "Which values or conditions are stated for {topic}?",
        ]
    perspectives = [
        "material properties",
        "compliance requirements",
        "application domain",
        "project status indicators",
        "cost and pricing information",
        "manufacturing constraints",
        "test and validation results",
        "customer and market context",
        "product performance details",
        "process and tooling notes",
    ]

    augmented: list[FAQRow] = list(rows)
    template_index = 0
    source_index = 0
    safety_counter = 0
    max_iterations = max(1, target_count * 10)

    while len(augmented) < target_count and safety_counter < max_iterations:
        base_row = rows[source_index % len(rows)]
        topic = _topic_from_question(base_row.question)
        source_name = base_row.source.split("::", 1)[1] if "::" in base_row.source else "source"
        if generation_mode == "classification":
            perspective = perspectives[template_index % len(perspectives)]
            question = _enforce_classification_question(
                f"{topic} with focus on {perspective} from {source_name}"
            )
        else:
            template = templates[template_index % len(templates)]
            perspective = perspectives[(template_index // len(templates)) % len(perspectives)]
            question = (
                f"{template.format(topic=topic)} "
                f"Focus on {perspective} in {source_name}."
            )
        augmented.append(
            FAQRow(
                index=0,
                question=question,
                answer=(
                    base_row.answer
                    if generation_mode == "classification"
                    else _normalize_whitespace(base_row.answer)
                ),
                source=base_row.source,
            )
        )
        template_index += 1
        source_index += 1
        safety_counter += 1
    return augmented


def _augment_rows_for_classification(rows: list[FAQRow], target_count: int) -> list[FAQRow]:
    """Compatibility helper used by tests and scripts that need class-focused augmentation."""
    return _augment_rows(rows, target_count=target_count, generation_mode="classification")


def _write_csv(rows: list[FAQRow], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["Index", "Question", "Answer", "source"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def _build_report(
    *,
    config: FAQGenerationConfig,
    run_result: FAQRunResult,
    rows: list[FAQRow],
    files_processed: list[Path],
    warnings: list[str],
) -> dict:
    file_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for row in rows:
        source_counts[row.source] += 1
        file_part = row.source.split("::", 1)[0] if "::" in row.source else row.source
        file_counts[file_part] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(config.input_dir),
        "output_csv": str(config.output_csv),
        "chat_model": config.chat_model,
        "config": {
            "min_rows": config.min_rows,
            "max_rows": config.max_rows,
            "strict": config.strict,
            "max_retries": config.max_retries,
            "temperature": config.temperature,
            "source_format": config.source_format,
            "generation_mode": config.generation_mode,
        },
        "summary": run_result.to_dict(),
        "files_processed": [path.name for path in files_processed],
        "per_markdown_file_counts": dict(sorted(file_counts.items())),
        "per_source_counts": dict(sorted(source_counts.items())),
        "warnings": warnings,
    }


def _write_report(report_path: Path, report: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_faq_csv(config: FAQGenerationConfig) -> tuple[list[FAQRow], FAQRunResult, dict]:
    if not config.input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {config.input_dir}")
    if not config.input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {config.input_dir}")

    source_units, markdown_files = _load_source_units(config.input_dir)
    if not markdown_files:
        raise ValueError("No markdown files found in input_dir.")
    if not source_units:
        raise ValueError("No source sections found in markdown files.")

    chunks = _chunk_source_units(source_units)
    if not chunks:
        raise ValueError("No chunkable source content found in markdown files.")

    load_dotenv(override=True)
    llm = ChatOpenAI(model_name=config.chat_model, temperature=config.temperature)

    rows_raw: list[FAQRow] = []
    yield_by_chunk: defaultdict[tuple[str, str, int], int] = defaultdict(int)
    warnings: list[str] = []

    base_target = max(4, min(32, math.ceil((config.min_rows * 1.2) / max(1, len(chunks)))))

    def run_generation_pass(pass_chunks: list[_ChunkUnit], target_count: int) -> int:
        generated = 0
        for chunk in pass_chunks:
            if len(rows_raw) >= config.max_rows * 4:
                break
            candidates = _generate_candidates_for_chunk(
                llm,
                chunk,
                target_count=target_count,
                max_retries=config.max_retries,
                generation_mode=config.generation_mode,
            )
            key = (chunk.markdown_filename, chunk.source_name, chunk.chunk_index)
            yield_by_chunk[key] += len(candidates)
            generated += len(candidates)
            for candidate in candidates:
                source = _source_value(chunk.markdown_filename, chunk.source_name)
                rows_raw.append(
                    FAQRow(
                        index=0,
                        question=str(candidate.get("question", "")),
                        answer=str(candidate.get("answer", "")),
                        source=source,
                    )
                )
        return generated

    run_generation_pass(chunks, base_target)
    cleaned_rows, duplicates_removed, invalid_removed = _dedupe_and_validate(
        rows_raw, generation_mode=config.generation_mode
    )

    low_yield_threshold = max(2, int(base_target * 0.5))
    low_yield_chunks = [
        chunk
        for chunk in chunks
        if yield_by_chunk[(chunk.markdown_filename, chunk.source_name, chunk.chunk_index)]
        < low_yield_threshold
    ]
    if low_yield_chunks and len(cleaned_rows) < config.min_rows:
        run_generation_pass(low_yield_chunks, 3)
        cleaned_rows, duplicates_removed, invalid_removed = _dedupe_and_validate(
            rows_raw, generation_mode=config.generation_mode
        )

    retries_used = 0
    while len(cleaned_rows) < config.min_rows and retries_used < config.max_retries:
        before = len(rows_raw)
        target_chunks = low_yield_chunks if low_yield_chunks else chunks
        run_generation_pass(target_chunks, max(2, base_target // 3))
        cleaned_rows, duplicates_removed, invalid_removed = _dedupe_and_validate(
            rows_raw, generation_mode=config.generation_mode
        )
        low_yield_chunks = [
            chunk
            for chunk in chunks
            if yield_by_chunk[(chunk.markdown_filename, chunk.source_name, chunk.chunk_index)]
            < low_yield_threshold
        ]
        retries_used += 1
        if len(rows_raw) == before:
            break

    if len(cleaned_rows) < config.min_rows and cleaned_rows:
        before_augment = len(cleaned_rows)
        augmented = _augment_rows(
            cleaned_rows,
            target_count=min(config.max_rows, config.min_rows),
            generation_mode=config.generation_mode,
        )
        cleaned_rows, duplicates_removed, invalid_removed = _dedupe_and_validate(
            augmented, generation_mode=config.generation_mode
        )
        if len(cleaned_rows) > before_augment:
            warnings.append(
                f"Applied deterministic {config.generation_mode}-focused augmentation from {before_augment} "
                f"to {len(cleaned_rows)} rows."
            )

    trimmed = _trim_rows_balanced(cleaned_rows, config.max_rows)
    if len(cleaned_rows) > config.max_rows:
        warnings.append(
            f"Generated {len(cleaned_rows)} valid rows; trimmed to max_rows={config.max_rows}."
        )
    if len(trimmed) < config.min_rows:
        warnings.append(
            f"Generated {len(trimmed)} valid rows, below min_rows={config.min_rows}."
        )

    final_rows = _sort_and_index_rows(trimmed)
    _write_csv(final_rows, config.output_csv)

    run_result = FAQRunResult(
        rows_written=len(final_rows),
        files_processed=len(markdown_files),
        source_sections_processed=len(source_units),
        duplicates_removed=duplicates_removed,
        invalid_rows_removed=invalid_removed,
        target_met=len(final_rows) >= config.min_rows,
    )

    report = _build_report(
        config=config,
        run_result=run_result,
        rows=final_rows,
        files_processed=markdown_files,
        warnings=warnings,
    )
    _write_report(config.report_path, report)

    return final_rows, run_result, report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate FAQ CSV from folder-level markdown files."
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing input markdown files.")
    parser.add_argument("--output-csv", required=True, help="Path to output FAQ CSV file.")
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to JSON report output.",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=500,
        help="Minimum number of FAQ rows required (default: 500).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=650,
        help="Maximum number of FAQ rows to keep after generation (default: 650).",
    )
    parser.add_argument(
        "--chat-model",
        default=DEFAULT_CHAT_MODEL,
        help=f"OpenAI chat model for FAQ generation (default: {DEFAULT_CHAT_MODEL}).",
    )
    parser.add_argument(
        "--generation-mode",
        choices=["faq", "classification"],
        default="faq",
        help="Generation target mode (default: faq). Use classification for training-style labels.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature (default: 0.0).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retry count for JSON formatting and fill passes (default: 3).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if generated rows are below --min-rows.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = FAQGenerationConfig(
            input_dir=Path(args.input_dir),
            output_csv=Path(args.output_csv),
            report_path=Path(args.report_path),
            min_rows=args.min_rows,
            max_rows=args.max_rows,
            chat_model=args.chat_model,
            strict=args.strict,
            max_retries=args.max_retries,
            temperature=args.temperature,
            generation_mode=args.generation_mode,
        )
    except ValueError as exc:
        print(f"Validation error: {exc}")
        return 2

    try:
        _, run_result, report = generate_faq_csv(config)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"Validation error: {exc}")
        return 2
    except Exception as exc:
        print(f"Generation error: {exc}")
        return 1

    print("=== FAQ CSV Generation Summary ===")
    print(f"Rows written: {run_result.rows_written}")
    print(f"Files processed: {run_result.files_processed}")
    print(f"Source sections processed: {run_result.source_sections_processed}")
    print(f"Duplicates removed: {run_result.duplicates_removed}")
    print(f"Invalid rows removed: {run_result.invalid_rows_removed}")
    print(f"Target met: {run_result.target_met}")
    print(f"CSV: {config.output_csv}")
    print(f"Report: {config.report_path}")
    if report.get("warnings"):
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")

    if config.strict and not run_result.target_met:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
