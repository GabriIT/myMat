from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}


@dataclass(slots=True)
class ParseConfig:
    knowledge_root: Path
    recursive: bool = True
    supported_extensions: set[str] = field(
        default_factory=lambda: set(DEFAULT_SUPPORTED_EXTENSIONS)
    )
    include_paths: list[Path] | None = None
    min_chars_pdf: int = 120
    min_chars_docx: int = 80
    min_chars_xlsx: int = 40
    min_chars_pptx: int = 120
    min_chars_pptx_slide: int = 40
    pptx_enable_vision: bool = False
    pptx_vision_provider: str = "ollama"
    pptx_vision_model: str = "qwen3.5:9b"
    pptx_vision_max_slides: int = 6
    pptx_vision_trigger_ratio: float = 0.25
    strict_mode: bool = False

    def __post_init__(self) -> None:
        self.knowledge_root = Path(self.knowledge_root).expanduser().resolve()
        self.supported_extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in self.supported_extensions
        }
        if self.include_paths is not None:
            self.include_paths = [Path(p).expanduser().resolve() for p in self.include_paths]
