"""Document parser abstraction layer for Engine 2.

Pluggable parsers: pdfplumber (default, free) | llamaparse (API).
"""

import io
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Vietnamese encoding / mojibake detection
# ──────────────────────────────────────────────

# Common Vietnamese diacritical characters (Unicode NFC)
_VIET_CHARS = set(
    "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợ"
    "ùúủũụưứừửữựỳýỷỹỵđ"
    "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ"
    "ÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ"
)

# Typical mojibake patterns from TCVN3 / VNI / VISCII fonts
_MOJIBAKE_PATTERNS = [
    # Digits replacing diacritics: "ch6y" instead of "cháy"
    # Upper-ASCII replacing Vietnamese: "DAm" instead of "Đảm"
    "6ng", "6y", "6n", "6i", "6o", "6c", "6t",  # digit 6 in wrong places
    "5n", "5t", "5i", "5o",  # digit 5
    "4n", "4i", "4t",  # digit 4
    "1f", "1i", "1n",  # digit 1
    "9 ", "Q ",  # isolated digits/letters replacing diacritics
    "OOi", "OO ",  # double-O replacing Đ
]


def detect_mojibake(text: str, sample_size: int = 2000) -> tuple[bool, float]:
    """Detect if extracted text has Vietnamese mojibake (encoding corruption).

    Heuristic: Vietnamese text should contain diacritical characters.
    If text is long but has very few Vietnamese diacritics AND has mojibake
    patterns, it's likely corrupted.

    Args:
        text: Extracted text to check
        sample_size: Max chars to analyze

    Returns:
        (is_mojibake: bool, confidence: float 0-1)
    """
    if not text or len(text.strip()) < 50:
        return False, 0.0

    sample = text[:sample_size]
    alpha_chars = [c for c in sample if c.isalpha()]
    if len(alpha_chars) < 20:
        return False, 0.0

    # Count Vietnamese diacritical characters
    viet_count = sum(1 for c in sample if c in _VIET_CHARS)
    viet_ratio = viet_count / len(alpha_chars)

    # Count mojibake pattern hits
    mojibake_hits = sum(1 for pat in _MOJIBAKE_PATTERNS if pat in sample)

    # Vietnamese text typically has 5-20% diacritical chars
    # If < 1% diacritics AND mojibake patterns present → likely corrupted
    if viet_ratio < 0.01 and mojibake_hits >= 3:
        confidence = min(1.0, 0.5 + mojibake_hits * 0.1)
        return True, confidence

    # Very few diacritics with many mojibake hits
    if viet_ratio < 0.03 and mojibake_hits >= 5:
        return True, 0.8

    return False, 0.0


@dataclass
class PageContent:
    """Content of a single page."""

    page_number: int
    text: str
    tables: list[str] = field(default_factory=list)  # Each table as Markdown


@dataclass
class ParseResult:
    """Result from document parsing."""

    markdown: str  # Full document as Markdown
    pages: list[PageContent] = field(default_factory=list)
    total_pages: int = 0
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base for document parsers."""

    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        """Parse a PDF file into structured text.

        Args:
            file_bytes: Raw file bytes
            filename: Original filename

        Returns:
            ParseResult with markdown text and per-page content
        """


class PdfPlumberParser(BaseParser):
    """CPU-only parser using pdfplumber. Reuses logic from Engine 1.

    Pros: Free, no external API, already installed.
    Cons: Cannot handle scanned/image-based PDFs.
    """

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        import pdfplumber

        pages: list[PageContent] = []
        all_text_parts: list[str] = []

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                page_text_parts: list[str] = []
                table_markdowns: list[str] = []

                # Extract tables first
                tables = page.extract_tables()
                table_areas = set()

                if tables:
                    for table_data in tables:
                        if not table_data:
                            continue
                        # Convert table to Markdown
                        md_table = self._table_to_markdown(table_data)
                        table_markdowns.append(md_table)
                        page_text_parts.append(md_table)

                    # Get bounding boxes of tables to exclude from text extraction
                    for tb in page.find_tables():
                        table_areas.add(tb.bbox)

                # Extract text outside tables
                if table_areas:
                    # Crop page to exclude table areas
                    text_outside = page.extract_text() or ""
                else:
                    text_outside = page.extract_text() or ""

                if text_outside.strip():
                    page_text_parts.insert(0, text_outside)

                page_content = "\n\n".join(page_text_parts)
                pages.append(
                    PageContent(
                        page_number=page_num,
                        text=page_content,
                        tables=table_markdowns,
                    )
                )

                all_text_parts.append(f"--- Page {page_num} ---\n{page_content}")

            total_pages = len(pdf.pages)

        markdown = "\n\n".join(all_text_parts)

        # Check for Vietnamese mojibake
        is_mojibake, mojibake_confidence = detect_mojibake(markdown)
        if is_mojibake:
            logger.warning(
                f"Detected Vietnamese mojibake in '{filename}' "
                f"(confidence={mojibake_confidence:.2f}). "
                f"Text extraction unreliable — recommend vision mode."
            )

        return ParseResult(
            markdown=markdown,
            pages=pages,
            total_pages=total_pages,
            metadata={
                "parser": "pdfplumber",
                "filename": filename,
                "mojibake_detected": is_mojibake,
                "mojibake_confidence": mojibake_confidence,
            },
        )

    @staticmethod
    def _table_to_markdown(table_data: list[list]) -> str:
        """Convert a table (list of rows) to Markdown table format."""
        if not table_data:
            return ""

        # Clean cells
        cleaned = []
        for row in table_data:
            cleaned.append([str(cell).strip() if cell else "" for cell in row])

        if not cleaned:
            return ""

        # Header
        header = cleaned[0]
        md_lines = ["| " + " | ".join(header) + " |"]
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Rows
        for row in cleaned[1:]:
            # Pad row if shorter than header
            padded = row + [""] * (len(header) - len(row))
            md_lines.append("| " + " | ".join(padded[:len(header)]) + " |")

        return "\n".join(md_lines)


class LlamaParseParser(BaseParser):
    """Cloud API parser using LlamaParse.

    Pros: Best quality for scanned PDFs, excellent table extraction.
    Cons: Costs $0.003/page, requires API key, sends data externally.
    """

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        try:
            from llama_parse import LlamaParse
        except ImportError:
            raise ImportError(
                "llama-parse is not installed. Install with: pip install llama-parse"
            )

        api_key = settings.LLAMAPARSE_API_KEY
        if not api_key:
            raise ValueError("LLAMAPARSE_API_KEY not configured")

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            parser = LlamaParse(
                api_key=api_key,
                result_type="markdown",
            )
            documents = parser.load_data(tmp_path)
            markdown = "\n\n".join(doc.text for doc in documents)

            pages = [
                PageContent(page_number=1, text=markdown, tables=[])
            ]

            return ParseResult(
                markdown=markdown,
                pages=pages,
                total_pages=len(documents),
                metadata={"parser": "llamaparse", "filename": filename},
            )
        finally:
            os.unlink(tmp_path)


# ──────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────

_PARSERS = {
    "pdfplumber": PdfPlumberParser,
    "llamaparse": LlamaParseParser,
}


def get_parser(parser_type: Optional[str] = None) -> BaseParser:
    """Get a document parser instance.

    Args:
        parser_type: Parser type name. Defaults to settings.DEFAULT_PARSER.

    Returns:
        BaseParser instance
    """
    parser_type = parser_type or settings.DEFAULT_PARSER
    cls = _PARSERS.get(parser_type)
    if cls is None:
        raise ValueError(
            f"Unknown parser '{parser_type}'. Available: {list(_PARSERS.keys())}"
        )
    return cls()
