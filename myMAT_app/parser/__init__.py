"""Parser package for multi-format knowledge ingestion."""

from .parser_config import ParseConfig
from .parser_types import FileParseResult, ParseIssue
from .parsers import parse_knowledge_base, parse_pptx_file
from .reporting import build_parse_report, print_parse_summary, write_parse_report

__all__ = [
    "ParseConfig",
    "ParseIssue",
    "FileParseResult",
    "parse_knowledge_base",
    "parse_pptx_file",
    "build_parse_report",
    "print_parse_summary",
    "write_parse_report",
]
