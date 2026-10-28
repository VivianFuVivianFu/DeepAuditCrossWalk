"""Bounded extraction for untrusted policy files; never interpret instructions."""

from __future__ import annotations

import io
import zipfile
from itertools import chain
from pathlib import PurePosixPath

from defusedxml import ElementTree
from docx import Document

from .documents import extract_document_from_pdf, extract_document_from_text

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_DOCX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_POLICY_CHARS = 5 * 1024 * 1024


def extract_policy_file(filename: str, content: bytes) -> str:
    if not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES:
        raise ValueError("Policy file exceeds the 20 MiB limit")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".pdf":
        return extract_document_from_pdf(content, document_name=filename).full_text
    if suffix in {".txt", ".md"}:
        return extract_document_from_text(
            content.decode("utf-8-sig"), filename
        ).full_text
    if suffix != ".docx":
        raise ValueError("Supported policy formats: PDF, DOCX, TXT and Markdown")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if (
                len(members) > 200
                or sum(item.file_size for item in members) > MAX_DOCX_UNPACKED_BYTES
            ):
                raise ValueError("DOCX archive exceeds extraction limits")
            if len({item.filename for item in members}) != len(members):
                raise ValueError("DOCX contains duplicate archive entries")
            for item in members:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                    raise ValueError("DOCX archive contains unsafe paths")
                if item.flag_bits & 1 or item.file_size > 200 * max(
                    1, item.compress_size
                ):
                    raise ValueError("DOCX archive exceeds compression limits")
                if item.filename.endswith((".xml", ".rels")):
                    ElementTree.fromstring(archive.read(item))
        document = Document(io.BytesIO(content))
        parts = []
        total = 0
        for text in chain(
            (paragraph.text for paragraph in document.paragraphs),
            (
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            ),
        ):
            total += len(text)
            if total > MAX_POLICY_CHARS:
                raise ValueError("Policy document exceeds the 5 MiB text limit")
            parts.append(text)
        return extract_document_from_text("\n".join(parts), filename).full_text
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("Invalid DOCX document") from exc
