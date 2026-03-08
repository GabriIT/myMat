from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

IssueSeverity = Literal["warning", "error"]
ParseStatus = Literal["success", "warning", "failed", "skipped"]


@dataclass(slots=True)
class ParseIssue:
    severity: IssueSeverity
    code: str
    message: str
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "suggested_action": self.suggested_action,
        }


@dataclass(slots=True)
class FileParseResult:
    source_path: str
    extension: str
    status: ParseStatus
    parser_used: str
    fallback_used: bool
    extracted_chars: int
    documents_count: int
    issues: list[ParseIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "extension": self.extension,
            "status": self.status,
            "parser_used": self.parser_used,
            "fallback_used": self.fallback_used,
            "extracted_chars": self.extracted_chars,
            "documents_count": self.documents_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }

