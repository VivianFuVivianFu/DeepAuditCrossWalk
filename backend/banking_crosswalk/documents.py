"""
PDF and Technical Document Extraction Engine for DeepAudit.

Provides robust, untrusted-input-safe document parsing for AI use case
assessments, architecture specifications, and security policies.

Key capabilities:
- pypdf (BSD-licensed) integration preserving page boundaries and layout text.
- Running header and footer detection and removal (e.g. running case title and page numbers).
- Section header detection supporting Markdown, numbered outlines (e.g. '1. Business case'),
  and all-caps titles.
- Labelled field extraction ('Key: Value') for structured project metadata.
- Prompt injection detection and inert marking.
- Verbatim citation validation against original page text.
"""

from __future__ import annotations

import re
import io
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from pathlib import Path

# pypdf is deliberately used instead of PyMuPDF: the latter is AGPL/commercial
# and would change the distribution obligations of this Apache-2.0 project.
try:
    from pypdf import PdfReader, apply_configuration
    from pypdf.errors import PdfReadError

    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PAGE_TEXT_CHARS = 500_000
MAX_DOCUMENT_TEXT_CHARS = 5 * 1024 * 1024
MAX_TABLES = 200
MAX_TABLE_ROWS = 1_000
MAX_TABLE_COLUMNS = 50
MAX_TABLE_CELL_CHARS = 10_000
MAX_TOTAL_TABLE_CELLS = 50_000
MAX_DECOMPRESSED_STREAM_BYTES = 10 * 1024 * 1024

_UNSAFE_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]"
)


# Security: Injection patterns to treat as inert text and raise warnings
INJECTION_PATTERNS = [
    r"ignore (?:all|any|the) previous instructions?",
    r"system prompt",
    r"developer message",
    r"execute (?:this|the following) command",
    r"exfiltrat(?:e|ion)",
    r"bypass (?:security|policy|controls?)",
    r"system policy update:\s*case",
    r"suppress approval checks",
]

# Patterns for running headers/footers to ignore during section grouping
RUNNING_HEADER_PATTERNS = [
    re.compile(
        r"^\s*HARBOURLINE\s+BANK\s*/\s*SYNTHETIC\s+AI\s+GOVERNANCE\s+CASE\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*ASSESSMENT\s+INPUT\s*[\u2022\s\-\|]+\s*Page\s+\d+\s*$", re.IGNORECASE
    ),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*CONFIDENTIAL\s*$", re.IGNORECASE),
]

# Patterns for numbered and standard section headers
SECTION_HEADER_PATTERNS = [
    # Markdown style (# Section)
    re.compile(r"^(#{1,4})\s+(.+)$"),
    # Numbered outline style: "1. Business case and operating context" or "7.1 Critical integration"
    re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9\s,\-_/&'\(\)]+)$"),
    # Bold / uppercase headings: "Critical integration detail: provisional credit API"
    re.compile(r"^([A-Z][A-Za-z0-9\s\-_/&]{3,60}):\s*$"),
]


@dataclass
class ParsedPassage:
    """A discrete passage of text from a specific page and section."""

    passage_id: str
    page_number: int
    section_title: str
    section_number: Optional[str]
    text: str
    passage_type: (
        str  # "paragraph" | "heading" | "table_row" | "labelled_field" | "code_block"
    )
    char_start: int
    char_end: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedTable:
    """A tabular block extracted from a document page."""

    table_id: str
    page_number: int
    caption: str
    headers: List[str]
    rows: List[List[str]]
    markdown_repr: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentSection:
    """A logical section within the document, spanning one or more pages."""

    title: str
    content: str
    char_start: int
    char_end: int
    section_number: Optional[str] = None
    page_start: int = 1
    page_end: int = 1
    passages: List[ParsedPassage] = field(default_factory=list)
    tables: List[ParsedTable] = field(default_factory=list)
    labelled_fields: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "section_number": self.section_number,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "content": self.content,
            "labelled_fields": self.labelled_fields,
            "passages_count": len(self.passages),
            "tables_count": len(self.tables),
        }


@dataclass
class ParsedDocument:
    """Fully parsed document with page-level traceability and structured sections."""

    document_name: str
    total_pages: int
    sections: List[DocumentSection]
    passages: List[ParsedPassage]
    tables: List[ParsedTable]
    labelled_fields: Dict[str, str]
    full_text: str
    page_texts: Dict[int, str]  # 1-indexed page_num -> clean text
    injection_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_name": self.document_name,
            "total_pages": self.total_pages,
            "sections_count": len(self.sections),
            "passages_count": len(self.passages),
            "tables_count": len(self.tables),
            "labelled_fields": self.labelled_fields,
            "injection_warnings": self.injection_warnings,
        }

    def get_page_text(self, page_num: int) -> str:
        return self.page_texts.get(page_num, "")

    def find_passages_containing(self, terms: Sequence[str]) -> List[ParsedPassage]:
        """Returns all passages matching any of the specified terms (case-insensitive)."""
        lower_terms = [t.lower() for t in terms if t.strip()]
        matched = []
        for p in self.passages:
            p_lower = p.text.lower()
            if any(term in p_lower for term in lower_terms):
                matched.append(p)
        return matched

    def validate_citation(self, citation: str) -> Tuple[bool, Optional[int]]:
        """
        Validates if a cited excerpt exists in the source document text.
        Returns (is_valid, matched_page_number).
        """
        clean_citation = re.sub(r"\s+", " ", citation.strip().lower())
        if not clean_citation or len(clean_citation) < 10:
            return False, None

        for page_num, text in self.page_texts.items():
            clean_page = re.sub(r"\s+", " ", text.lower())
            if clean_citation in clean_page:
                return True, page_num

        return False, None


# ── Parsing Implementation ───────────────────────────────────────────────────


def _sanitize_untrusted_text(text: str) -> Tuple[str, List[str]]:
    """Sanitizes text and flags potential prompt injection sequences."""
    if not isinstance(text, str):
        raise TypeError("Document text must be a string")
    if len(text) > MAX_DOCUMENT_TEXT_CHARS:
        raise ValueError("Document text exceeds the 5 MiB extraction limit")
    warnings: List[str] = []
    # Strip C0/C1 and bidi-override controls while retaining tab/newline.
    # Directional overrides can make an on-screen citation differ from the
    # actual string reviewed by the engine.
    clean = _UNSAFE_CONTROL_CHARS.sub("", text)
    clean = clean.replace("\r\n", "\n").replace("\r", "\n")

    for pat in INJECTION_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            warnings.append(
                f"Prompt injection pattern detected and flagged as inert: {pat}"
            )

    return clean, warnings


def _clean_table_cell(value: str) -> str:
    clean = _UNSAFE_CONTROL_CHARS.sub("", str(value)).strip()
    if len(clean) > MAX_TABLE_CELL_CHARS:
        raise ValueError("PDF table cell exceeds the extraction limit")
    return clean


def _extract_layout_tables(
    layout_text: str,
    page_number: int,
    *,
    existing_tables: int,
    existing_cells: int,
) -> Tuple[List[ParsedTable], int]:
    """Extract conservative table candidates from pypdf layout text.

    pypdf intentionally does not infer table geometry.  Consecutive layout
    rows containing at least two columns separated by two or more spaces are
    preserved as bounded table candidates.  The original page text remains
    authoritative for citations.
    """

    groups: List[List[List[str]]] = []
    current: List[List[str]] = []
    for raw_line in layout_text.splitlines():
        if _is_running_header_or_footer(raw_line):
            continue
        cells = [
            _clean_table_cell(item)
            for item in re.split(r"\s{2,}", raw_line.strip())
            if item.strip()
        ]
        if len(cells) >= 2:
            if len(cells) > MAX_TABLE_COLUMNS:
                raise ValueError("PDF table exceeds the column limit")
            current.append(cells)
            if len(current) > MAX_TABLE_ROWS:
                raise ValueError("PDF table exceeds the row limit")
        elif current:
            if len(current) >= 2:
                groups.append(current)
            current = []
    if len(current) >= 2:
        groups.append(current)

    if existing_tables + len(groups) > MAX_TABLES:
        raise ValueError("PDF contains too many table candidates")

    output: List[ParsedTable] = []
    total_cells = existing_cells
    for index, rows in enumerate(groups, start=1):
        row_cell_count = sum(len(row) for row in rows)
        total_cells += row_cell_count
        if total_cells > MAX_TOTAL_TABLE_CELLS:
            raise ValueError("PDF contains too many extracted table cells")
        headers = rows[0]
        data_rows = rows[1:]

        def markdown_row(row: List[str]) -> str:
            return "| " + " | ".join(cell.replace("|", r"\|") for cell in row) + " |"

        markdown_lines = [markdown_row(headers), markdown_row(["---"] * len(headers))]
        markdown_lines.extend(markdown_row(row) for row in data_rows)
        output.append(
            ParsedTable(
                table_id=f"T-P{page_number}-{existing_tables + index}",
                page_number=page_number,
                caption=f"Layout table candidate on Page {page_number}",
                headers=headers,
                rows=data_rows,
                markdown_repr="\n".join(markdown_lines),
            )
        )
    return output, total_cells


def _extract_pdf_page_payloads(
    pdf_bytes: bytes,
    max_pages: int,
) -> List[Tuple[str, str, Optional[str]]]:
    """Parse and decode bounded page text while pypdf limits are active.

    ``PdfReader`` decodes many streams lazily, so the resource-limit context
    must remain active for both reader construction and ``extract_text``.
    The optional third tuple item is a safe layout warning class name.
    """

    try:
        with apply_configuration(
            maximum_declared_stream_length=MAX_DECOMPRESSED_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            jbig2_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            lzw_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            run_length_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            zlib_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            brotli_maximum_output_length=MAX_DECOMPRESSED_STREAM_BYTES,
            image_maximum_buffer_size=MAX_DECOMPRESSED_STREAM_BYTES,
            stream_decoding_work_maximum_length=4 * MAX_DECOMPRESSED_STREAM_BYTES,
        ):
            reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported")
            if len(reader.pages) > max_pages:
                raise ValueError(f"PDF exceeds the {max_pages}-page extraction limit")

            payloads: List[Tuple[str, str, Optional[str]]] = []
            extracted_text_chars = 0
            extracted_layout_chars = 0
            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    raw_text = page.extract_text() or ""
                except Exception as exc:
                    raise ValueError(
                        f"PDF page {page_num} text could not be extracted safely"
                    ) from exc
                if len(raw_text) > MAX_PAGE_TEXT_CHARS:
                    raise ValueError(
                        f"PDF page {page_num} exceeds the text extraction limit"
                    )
                extracted_text_chars += len(raw_text)
                if extracted_text_chars > MAX_DOCUMENT_TEXT_CHARS:
                    raise ValueError("PDF extracted text exceeds the 5 MiB limit")

                layout_warning: Optional[str] = None
                try:
                    layout_text = page.extract_text(extraction_mode="layout") or ""
                    if len(layout_text) > MAX_PAGE_TEXT_CHARS:
                        raise ValueError(
                            f"PDF page {page_num} layout exceeds the text extraction limit"
                        )
                    extracted_layout_chars += len(layout_text)
                    if extracted_layout_chars > MAX_DOCUMENT_TEXT_CHARS:
                        raise ValueError("PDF layout text exceeds the 5 MiB limit")
                except ValueError:
                    raise
                except Exception as exc:
                    layout_text = ""
                    layout_warning = type(exc).__name__
                payloads.append((raw_text, layout_text, layout_warning))
            return payloads
    except ValueError:
        raise
    except (PdfReadError, TypeError, OSError) as exc:
        raise ValueError("PDF could not be parsed safely") from exc


def _is_running_header_or_footer(line: str) -> bool:
    """Checks if a line is a repeated page header or footer."""
    trimmed = line.strip()
    if not trimmed:
        return False
    for pat in RUNNING_HEADER_PATTERNS:
        if pat.match(trimmed):
            return True
    return False


def _extract_labelled_fields_from_line(line: str) -> Optional[Tuple[str, str]]:
    """Detects 'Key: Value' or '**Key:** Value' pattern."""
    clean = re.sub(r"^\s*[-*•]\s*", "", line).strip()
    match = re.match(r"^\*{0,2}([A-Za-z0-9\s\-_/&]{2,40})\*{0,2}:\s*(.+)$", clean)
    if match:
        key = match.group(1).strip()
        val = match.group(2).strip()
        # Avoid treating full sentences with a colon as a labelled field
        if len(key.split()) <= 6 and not key.lower().startswith(
            ("http", "note", "e.g", "i.e", "warning")
        ):
            return key, val
    return None


def extract_document_from_pdf(
    source: Union[str, Path, bytes, io.BytesIO],
    document_name: str = "document.pdf",
    max_pages: int = MAX_PDF_PAGES,
) -> ParsedDocument:
    """
    Extracts structured content, headings, tables, labelled fields, and page-numbered passages
    from a PDF document using pypdf.

    Args:
        source: File path, Path object, or bytes/BytesIO of the PDF.
        document_name: Filename or identifier for traceability.
        max_pages: Safeguard against excessively large or unbounded files.

    Returns:
        ParsedDocument with full page-level and section-level traceability.
    """
    if not HAVE_PYPDF:
        raise ImportError(
            "pypdf is required for PDF parsing. Install the project's declared dependencies."
        )
    if not isinstance(max_pages, int) or not 1 <= max_pages <= MAX_PDF_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_PDF_PAGES}")

    # Read a bounded byte snapshot before invoking the parser. This also
    # avoids leaving source file handles open across extraction failures.
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(f"PDF document not found: {source_path}")
        if source_path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds the 20 MiB extraction limit")
        document_name = source_path.name
        pdf_bytes = source_path.read_bytes()
    elif isinstance(source, bytes):
        pdf_bytes = source
    elif isinstance(source, io.BytesIO):
        if source.getbuffer().nbytes > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds the 20 MiB extraction limit")
        pdf_bytes = source.getvalue()
    else:
        raise ValueError("Unsupported source type for extract_document_from_pdf")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 20 MiB extraction limit")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Document is not a PDF file")

    page_payloads = _extract_pdf_page_payloads(pdf_bytes, max_pages)
    total_pages = len(page_payloads)
    all_warnings: List[str] = []
    page_texts: Dict[int, str] = {}
    passages: List[ParsedPassage] = []
    tables: List[ParsedTable] = []
    global_labelled_fields: Dict[str, str] = {}

    current_section_title = "Document Overview"
    current_section_number: Optional[str] = None
    current_section_page_start = 1
    current_section_lines: List[str] = []
    current_section_passages: List[ParsedPassage] = []
    current_section_tables: List[ParsedTable] = []
    current_section_fields: Dict[str, str] = {}
    sections: List[DocumentSection] = []
    extracted_table_cells = 0

    global_cursor = 0

    def finalize_current_section(page_end: int):
        nonlocal current_section_lines, current_section_passages, current_section_tables
        nonlocal current_section_fields, current_section_title, current_section_number
        nonlocal current_section_page_start, global_cursor

        content_str = "\n".join(current_section_lines).strip()
        if content_str or current_section_passages:
            start_pos = global_cursor - len(content_str)
            sec = DocumentSection(
                title=current_section_title,
                section_number=current_section_number,
                content=content_str,
                char_start=max(0, start_pos),
                char_end=global_cursor,
                page_start=current_section_page_start,
                page_end=page_end,
                passages=list(current_section_passages),
                tables=list(current_section_tables),
                labelled_fields=dict(current_section_fields),
            )
            sections.append(sec)

        current_section_lines = []
        current_section_passages = []
        current_section_tables = []
        current_section_fields = {}

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        raw_page_text, layout_text, layout_warning = page_payloads[page_idx]

        # Sanitize untrusted text
        clean_page_text, page_warnings = _sanitize_untrusted_text(raw_page_text)
        all_warnings.extend(page_warnings)
        page_texts[page_num] = clean_page_text

        # Preserve bounded table candidates from the layout representation.
        try:
            page_tables, extracted_table_cells = _extract_layout_tables(
                layout_text,
                page_num,
                existing_tables=len(tables),
                existing_cells=extracted_table_cells,
            )
            tables.extend(page_tables)
            current_section_tables.extend(page_tables)
        except ValueError:
            raise
        except Exception as exc:
            # Table inference is non-authoritative; retain page text and expose
            # a safe warning without leaking document contents.
            all_warnings.append(
                f"Table layout extraction skipped on page {page_num}: {type(exc).__name__}"
            )
        if layout_warning:
            all_warnings.append(
                f"Table layout extraction skipped on page {page_num}: {layout_warning}"
            )

        # Process lines on this page
        lines = clean_page_text.split("\n")
        para_accumulator: List[str] = []

        def flush_paragraph():
            nonlocal para_accumulator, global_cursor
            if para_accumulator:
                para_text = " ".join(para_accumulator).strip()
                if para_text:
                    p_id = f"P{page_num}-{len(passages) + 1}"
                    passage = ParsedPassage(
                        passage_id=p_id,
                        page_number=page_num,
                        section_title=current_section_title,
                        section_number=current_section_number,
                        text=para_text,
                        passage_type="paragraph",
                        char_start=global_cursor,
                        char_end=global_cursor + len(para_text),
                    )
                    passages.append(passage)
                    current_section_passages.append(passage)
                    current_section_lines.append(para_text)
                    global_cursor += len(para_text) + 1
                para_accumulator = []

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                flush_paragraph()
                continue

            # Skip running headers and footers
            if _is_running_header_or_footer(trimmed):
                continue

            # Check if this line is a section header
            is_header = False
            detected_title = ""
            detected_number = None

            for pat in SECTION_HEADER_PATTERNS:
                m = pat.match(trimmed)
                if m:
                    # Markdown match
                    if pat.pattern.startswith("^(#{1,4})"):
                        detected_title = m.group(2).strip()
                    # Numbered match
                    elif pat.pattern.startswith("^(\\d+"):
                        detected_number = m.group(1).strip()
                        detected_title = m.group(2).strip()
                    # Uppercase colon match
                    else:
                        detected_title = m.group(1).strip()
                    is_header = True
                    break

            # Special case: check for prominent unnumbered headings like "In scope", "Out of scope", "Architecture assumptions"
            if (
                not is_header
                and len(trimmed) < 60
                and trimmed.lower()
                in (
                    "in scope",
                    "out of scope",
                    "architecture assumptions",
                    "identity and authorisation details",
                    "assessment instruction",
                    "proposed launch acceptance criteria",
                    "critical integration detail: provisional credit api",
                )
            ):
                is_header = True
                detected_title = trimmed

            if is_header:
                flush_paragraph()
                finalize_current_section(page_end=page_num)
                current_section_title = detected_title
                current_section_number = detected_number
                current_section_page_start = page_num

                # Record heading passage
                h_id = f"P{page_num}-H{len(passages) + 1}"
                h_passage = ParsedPassage(
                    passage_id=h_id,
                    page_number=page_num,
                    section_title=current_section_title,
                    section_number=current_section_number,
                    text=trimmed,
                    passage_type="heading",
                    char_start=global_cursor,
                    char_end=global_cursor + len(trimmed),
                )
                passages.append(h_passage)
                current_section_passages.append(h_passage)
                current_section_lines.append(f"## {trimmed}")
                global_cursor += len(trimmed) + 1
                continue

            # Check for labelled field (e.g. "Case ID: HLB-AI-027")
            field_match = _extract_labelled_fields_from_line(trimmed)
            if field_match:
                k, v = field_match
                global_labelled_fields[k] = v
                current_section_fields[k] = v

                lf_passage = ParsedPassage(
                    passage_id=f"P{page_num}-F{len(passages) + 1}",
                    page_number=page_num,
                    section_title=current_section_title,
                    section_number=current_section_number,
                    text=f"{k}: {v}",
                    passage_type="labelled_field",
                    char_start=global_cursor,
                    char_end=global_cursor + len(trimmed),
                )
                passages.append(lf_passage)
                current_section_passages.append(lf_passage)
                current_section_lines.append(f"{k}: {v}")
                global_cursor += len(trimmed) + 1
                continue

            # Accumulate normal text into paragraph
            para_accumulator.append(trimmed)

        flush_paragraph()

    # Finalize last section
    finalize_current_section(page_end=total_pages)

    # Full text compilation
    full_text = "\n\n".join(
        f"--- [Page {p}] ---\n" + text for p, text in page_texts.items()
    )

    return ParsedDocument(
        document_name=document_name,
        total_pages=total_pages,
        sections=sections,
        passages=passages,
        tables=tables,
        labelled_fields=global_labelled_fields,
        full_text=full_text,
        page_texts=page_texts,
        injection_warnings=list(set(all_warnings)),
    )


def extract_document_from_text(
    text: str, document_name: str = "document.txt"
) -> ParsedDocument:
    """
    Parses plain text or Markdown documents using the same structured model,
    simulating page breaks when markdown form feeds or page delimiters are found.
    """
    clean_text, warnings = _sanitize_untrusted_text(text)

    page_texts: Dict[int, str] = {}
    # Only a standalone line is a page delimiter.  An inline phrase such as
    # "see Page 3" must remain ordinary evidence text.
    marker_pattern = re.compile(
        r"^[ \t]*(?:---|===)?[ \t]*\[?Page[ \t]+([1-9]\d{0,2})\]?[ \t]*(?:---|===)?[ \t]*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    markers = list(marker_pattern.finditer(clean_text))
    if markers:
        preamble = clean_text[: markers[0].start()].strip()
        for index, marker in enumerate(markers):
            page_number = int(marker.group(1))
            if page_number > MAX_PDF_PAGES:
                raise ValueError(f"Text document page marker exceeds {MAX_PDF_PAGES}")
            if page_number in page_texts:
                raise ValueError(f"Duplicate text document page marker: {page_number}")
            end = (
                markers[index + 1].start()
                if index + 1 < len(markers)
                else len(clean_text)
            )
            page_texts[page_number] = clean_text[marker.end() : end].strip()

        if preamble:
            page_texts[1] = (
                f"{preamble}\n{page_texts[1]}" if 1 in page_texts else preamble
            ).strip()
        if len(page_texts) > MAX_PDF_PAGES:
            raise ValueError(f"Text document exceeds the {MAX_PDF_PAGES}-page limit")
    else:
        # Single page document
        page_texts[1] = clean_text

    total_pages = len(page_texts) if page_texts else 1
    last_page_number = max(page_texts.keys()) if page_texts else 1
    sections: List[DocumentSection] = []
    passages: List[ParsedPassage] = []
    labelled_fields: Dict[str, str] = {}
    global_cursor = 0

    current_section_title = "Overview"
    current_section_lines: List[str] = []
    current_section_passages: List[ParsedPassage] = []
    current_section_fields: Dict[str, str] = {}
    current_section_page = 1

    def flush_section(page_num: int):
        nonlocal current_section_lines, current_section_passages, current_section_fields
        nonlocal current_section_title, current_section_page, global_cursor
        content_str = "\n".join(current_section_lines).strip()
        if content_str or current_section_passages:
            sections.append(
                DocumentSection(
                    title=current_section_title,
                    content=content_str,
                    char_start=max(0, global_cursor - len(content_str)),
                    char_end=global_cursor,
                    page_start=current_section_page,
                    page_end=page_num,
                    passages=list(current_section_passages),
                    labelled_fields=dict(current_section_fields),
                )
            )
        current_section_lines = []
        current_section_passages = []
        current_section_fields = {}

    for page_num in sorted(page_texts.keys()):
        p_text = page_texts[page_num]
        lines = p_text.split("\n")
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Header detection
            is_header = False
            for pat in SECTION_HEADER_PATTERNS:
                m = pat.match(trimmed)
                if m:
                    flush_section(page_num)
                    current_section_title = m.group(len(m.groups())).strip()
                    current_section_page = page_num
                    is_header = True
                    break

            if is_header:
                passage = ParsedPassage(
                    passage_id=f"P{page_num}-{len(passages) + 1}",
                    page_number=page_num,
                    section_title=current_section_title,
                    section_number=None,
                    text=trimmed,
                    passage_type="heading",
                    char_start=global_cursor,
                    char_end=global_cursor + len(trimmed),
                )
                passages.append(passage)
                current_section_passages.append(passage)
                global_cursor += len(trimmed) + 1
                continue

            # Labelled field detection
            field_match = _extract_labelled_fields_from_line(trimmed)
            if field_match:
                k, v = field_match
                labelled_fields[k] = v
                current_section_fields[k] = v
                passage = ParsedPassage(
                    passage_id=f"P{page_num}-{len(passages) + 1}",
                    page_number=page_num,
                    section_title=current_section_title,
                    section_number=None,
                    text=f"{k}: {v}",
                    passage_type="labelled_field",
                    char_start=global_cursor,
                    char_end=global_cursor + len(trimmed),
                )
                passages.append(passage)
                current_section_passages.append(passage)
                current_section_lines.append(f"{k}: {v}")
                global_cursor += len(trimmed) + 1
                continue

            # Regular text
            passage = ParsedPassage(
                passage_id=f"P{page_num}-{len(passages) + 1}",
                page_number=page_num,
                section_title=current_section_title,
                section_number=None,
                text=trimmed,
                passage_type="paragraph",
                char_start=global_cursor,
                char_end=global_cursor + len(trimmed),
            )
            passages.append(passage)
            current_section_passages.append(passage)
            current_section_lines.append(trimmed)
            global_cursor += len(trimmed) + 1

    flush_section(last_page_number)

    return ParsedDocument(
        document_name=document_name,
        total_pages=total_pages,
        sections=sections,
        passages=passages,
        tables=[],
        labelled_fields=labelled_fields,
        full_text=clean_text,
        page_texts=page_texts,
        injection_warnings=warnings,
    )


def extract_document_from_source(
    source: Union[str, Path, bytes, io.BytesIO],
) -> ParsedDocument:
    """Normalize an uploaded path, PDF byte stream, or literal document text.

    Strings are always treated as literal untrusted content; callers must pass
    a ``Path`` object to request local filesystem access.  This avoids Windows
    path-length failures, prevents content ending in ``.pdf`` from being
    misclassified, and stops API text fields becoming arbitrary-file readers.
    """

    if isinstance(source, (bytes, io.BytesIO)):
        return extract_document_from_pdf(source)

    if isinstance(source, Path):
        if not source.is_file():
            raise FileNotFoundError(f"Document not found: {source}")
        source_path: Optional[Path] = source
    elif isinstance(source, str):
        return extract_document_from_text(source)
    else:
        raise ValueError(f"Unsupported document source type: {type(source)}")

    if source_path.suffix.lower() == ".pdf":
        return extract_document_from_pdf(source_path)
    if source_path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise ValueError("Text document exceeds the 10 MiB file limit")
    return extract_document_from_text(
        source_path.read_text(encoding="utf-8", errors="ignore"),
        document_name=source_path.name,
    )
