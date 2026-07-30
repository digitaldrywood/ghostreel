#!/usr/bin/env python3
"""Parse narration written as plain Markdown prose paragraphs."""

from __future__ import annotations

from dataclasses import dataclass
import re


BLOCK_MARKER_RE = re.compile(
    r"^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\||-{3,}$|_{3,}$|\*{3,}$|<)"
)
SPEAKER_TAG_RE = re.compile(r"^\[([A-Za-z][A-Za-z0-9_-]*)\]\s+(.+)$")


@dataclass(frozen=True)
class Paragraph:
    line: int
    text: str
    speaker: str | None = None


class ProseFormatError(ValueError):
    """Raised when narration includes storyboard or layout markup."""


def parse_prose(raw: str) -> tuple[Paragraph, ...]:
    """Return one beat-sized thought per blank-line-delimited paragraph.

    Authors may wrap a paragraph across lines. Headings, lists, block quotes,
    tables, and fenced blocks are rejected because a narration script is prose,
    not a visual layout or a place to hide production notes.
    """

    paragraphs: list[Paragraph] = []
    lines: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal lines, start_line
        if lines:
            text = " ".join(line.strip() for line in lines)
            match = SPEAKER_TAG_RE.match(text)
            paragraphs.append(
                Paragraph(
                    start_line,
                    match.group(2) if match else text,
                    match.group(1) if match else None,
                )
            )
        lines = []
        start_line = 0

    for number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith(("```", "~~~")):
            raise ProseFormatError(
                f"line {number}: fenced blocks are not allowed in narration prose"
            )
        if BLOCK_MARKER_RE.match(stripped) or "|" in stripped:
            raise ProseFormatError(
                f"line {number}: headings, lists, quotes, and tables are not "
                "allowed in narration prose"
            )
        if not lines:
            start_line = number
        lines.append(line)

    flush()
    if not paragraphs:
        raise ProseFormatError("the script contains no prose paragraphs")
    return tuple(paragraphs)
