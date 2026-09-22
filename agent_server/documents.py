"""Turning a source document's bytes into text the agent can read.

The `/wiki/raw/` tier holds what people put there, and people do not only put
markdown there. A `.docx` is a ZIP of XML, so it has to be *extracted* rather
than decoded — `bytes.decode("utf-8")` raises on it, which is why the tier
previously showed such a file in `ls` and refused it everywhere else.

Extraction is kept here rather than in `backends.py` because it is a different
concern: one module knows the Files API, this one knows document formats. It
also means the extraction is testable without a Volume or a client.

**What this does not do.** It recovers text, not fidelity. Styling, images,
headers and footers are dropped. Tables are kept, rendered as markdown, because
a policy document keeps its targets in a table and losing the rows would lose
the only part the agent needs. Rendering them as markdown rather than as loose
lines is deliberate: every other document in the bundle states its targets in a
markdown table, so the extracted text reads like the corpus around it.
"""

from __future__ import annotations

import io
import logging
from typing import Iterator

logger = logging.getLogger(__name__)

DOCX_SUFFIX = ".docx"


class UnreadableDocumentError(ValueError):
    """A file whose bytes could not be turned into document text."""


def is_extractable(file_path: str) -> bool:
    """Whether this path names a format we extract rather than decode."""
    return file_path.lower().endswith(DOCX_SUFFIX)


def decode(raw: bytes, file_path: str) -> str:
    """The document's text, however this format carries it.

    The single entry point both the read path and the search scan use, so a
    format understood by one is understood by the other. A tier where `read`
    succeeds and `grep` silently skips the same file is worse than one that
    refuses it twice.
    """
    if is_extractable(file_path):
        return docx_text(raw, file_path)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnreadableDocumentError(
            f"File '{file_path}' is not UTF-8 text and cannot be read as a document"
        ) from exc


def docx_text(raw: bytes, file_path: str = "<docx>") -> str:
    """A `.docx` as plain text, with its tables rendered as markdown.

    Blocks are walked in document order rather than paragraphs-then-tables:
    `python-docx` exposes the two as separate collections, and reading them in
    turn would move every table to the end, detaching a target table from the
    heading that says what it targets.
    """
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise UnreadableDocumentError(
            f"File '{file_path}' is a .docx but python-docx is not installed"
        ) from exc

    try:
        document = Document(io.BytesIO(raw))
    except Exception as exc:
        # A truncated upload or a mislabelled file arrives here. Raised as our
        # own error so the caller reports it as a tool result the agent can act
        # on, rather than as an exception that ends the turn.
        raise UnreadableDocumentError(
            f"File '{file_path}' could not be read as a Word document: {exc}"
        ) from exc

    parts: list[str] = []
    for block in _blocks(document):
        rendered = block if isinstance(block, str) else _table_markdown(block)
        if rendered.strip():
            parts.append(rendered)
    return "\n\n".join(parts) + "\n" if parts else ""


def _blocks(document) -> Iterator:
    """Paragraph text and tables, in the order the document holds them."""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document).text
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _table_markdown(table) -> str:
    """A Word table as a markdown table.

    Cells are padded to the header's width and their newlines flattened: a row
    that is short or that wraps produces a table markdown will not render, and a
    broken table is harder to read than a plain one.
    """
    rows = [[_cell(c.text) for c in row.cells] for row in table.rows]
    if not rows:
        return ""
    width = len(rows[0])
    header, *body = [(r + [""] * width)[:width] for r in rows]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * width) + "|",
    ]
    lines.extend("| " + " | ".join(r) + " |" for r in body)
    return "\n".join(lines)


def _cell(text: str) -> str:
    """One cell's text, safe to place between pipes."""
    return " ".join(text.split()).replace("|", "\\|")
