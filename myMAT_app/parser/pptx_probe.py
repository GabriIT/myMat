from __future__ import annotations

import argparse
import json
from pathlib import Path

from .parser_config import ParseConfig
from .parsers import parse_pptx_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe a single PPTX file with the myMAT parser and write a structured report."
    )
    parser.add_argument(
        "--pptx-path",
        required=True,
        help="Path to the .pptx file to parse.",
    )
    parser.add_argument(
        "--report-path",
        required=True,
        help="Path to JSON output report.",
    )
    parser.add_argument(
        "--enable-vision",
        action="store_true",
        help="Enable optional selective vision enrichment.",
    )
    parser.add_argument(
        "--max-vision-slides",
        type=int,
        default=6,
        help="Maximum number of slides to enrich with vision (default: 6).",
    )
    parser.add_argument(
        "--vision-model",
        default="qwen3.5:9b",
        help="Vision model name for Ollama (default: qwen3.5:9b).",
    )
    parser.add_argument(
        "--min-chars-pptx",
        type=int,
        default=120,
        help="Minimum expected character count for PPTX (default: 120).",
    )
    parser.add_argument(
        "--min-chars-pptx-slide",
        type=int,
        default=40,
        help="Minimum expected chars per slide before low-text classification (default: 40).",
    )
    parser.add_argument(
        "--vision-trigger-ratio",
        type=float,
        default=0.25,
        help="Auto-vision trigger when low-text slide ratio reaches this value (default: 0.25).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    pptx_path = Path(args.pptx_path).expanduser().resolve()
    report_path = Path(args.report_path).expanduser().resolve()

    if not pptx_path.exists() or not pptx_path.is_file():
        print(f"Validation error: PPTX path does not exist or is not a file: {pptx_path}")
        return 2
    if pptx_path.suffix.lower() != ".pptx":
        print(f"Validation error: expected a .pptx file, got: {pptx_path.name}")
        return 2

    config = ParseConfig(
        knowledge_root=pptx_path.parent,
        recursive=False,
        supported_extensions={".pptx"},
        min_chars_pptx=args.min_chars_pptx,
        min_chars_pptx_slide=args.min_chars_pptx_slide,
        pptx_enable_vision=args.enable_vision,
        pptx_vision_model=args.vision_model,
        pptx_vision_max_slides=max(1, args.max_vision_slides),
        pptx_vision_trigger_ratio=max(0.0, min(1.0, args.vision_trigger_ratio)),
    )

    try:
        docs, result = parse_pptx_file(pptx_path, config)
    except Exception as exc:
        print(f"PPTX probe failed: {exc}")
        return 1

    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "file": str(pptx_path),
        "result": result.to_dict(),
        "documents": {
            "count": len(docs),
            "sample": [
                {
                    "slide_number": doc.metadata.get("slide_number"),
                    "slide_title": doc.metadata.get("slide_title"),
                    "visual_enriched": doc.metadata.get("visual_enriched"),
                    "char_count": len(doc.page_content),
                    "preview": doc.page_content[:400],
                }
                for doc in docs[:5]
            ],
        },
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== PPTX Probe Summary ===")
    print(f"File: {pptx_path}")
    print(f"Status: {result.status}")
    print(f"Parser used: {result.parser_used}")
    print(f"Fallback used: {result.fallback_used}")
    print(f"Extracted chars: {result.extracted_chars}")
    print(f"Documents emitted: {result.documents_count}")
    print(f"Report: {report_path}")

    if result.status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
