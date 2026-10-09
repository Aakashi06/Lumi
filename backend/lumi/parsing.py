"""Bounded local PDF, DOCX and UTF-8 text readers."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class Passage:
    text: str
    reference: dict


def pdf(path: str) -> tuple[str, list[Passage]]:
    with pymupdf.open(path) as document:
        if document.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")
        if len(document) > 300:
            raise ValueError("PDFs are limited to 300 pages")
        passages = [
            Passage(page.get_text(), {"page": index + 1}) for index, page in enumerate(document)
        ]
        if sum(len(p.text.strip()) for p in passages) < 50:
            raise ValueError("No readable text found. Scanned PDFs require OCR before upload.")
        return Path(path).stem, passages


def document_file(kind: str, path: str) -> tuple[str, list[Passage]]:
    if kind == "pdf":
        return pdf(path)
    if kind == "docx":
        from docx import Document

        document = Document(path)
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        paragraphs.extend(
            " | ".join(cell.text for cell in row.cells)
            for table in document.tables
            for row in table.rows
        )
        text = "\n\n".join(paragraphs)
    else:
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeError as error:
            raise ValueError("Save the text file with UTF-8 encoding and try again.") from error
        if "\x00" in text:
            raise ValueError("Upload a plain text file, not a binary file.")
    if len(text.strip()) < 30:
        raise ValueError("The document needs at least 30 characters of readable text.")
    return Path(path).stem, [Passage(text, {"document": Path(path).name})]


async def read_source(kind: str, url: str | None, file_path: str | None):
    if kind not in {"pdf", "docx", "txt"} or not file_path:
        raise ValueError("Upload a PDF, Word (.docx), or plain text file.")
    return await asyncio.to_thread(document_file, kind, file_path)
