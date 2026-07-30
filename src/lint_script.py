#!/usr/bin/env python3
"""Gate narration rhythm and writing rules before storyboard generation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any, Iterable


WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:[\"'”’)\]]*)\s+")


@dataclass(frozen=True)
class Threshold:
    label: str
    direction: str
    value: float


# Starting voice envelope from issue #13, calibrated against the repository
# owner's prose in README.md, docs/the-method.md, and KNOWN-ISSUES.md.
THRESHOLDS = {
    "mean_words": Threshold("mean sentence length", "minimum", 12.0),
    "stddev_words": Threshold("sentence-length standard deviation", "minimum", 6.5),
    "long_sentence_percent": Threshold("sentences with at least 20 words", "minimum", 10.0),
    "over_30_count": Threshold("sentences over 30 words", "minimum", 1.0),
    "short_sentence_percent": Threshold("sentences with at most 6 words", "maximum", 25.0),
}

BANNED_TERMS = (
    "delve",
    "foster",
    "leverage",
    "utilize",
    "facilitate",
    "empower",
    "streamline",
    "robust",
    "cutting-edge",
    "paradigm shift",
    "game changer",
    "tapestry",
    "realm",
    "beacon",
    "multifaceted",
    "meticulous",
    "intricate",
    "paramount",
    "transformative",
    "elevate",
    "embark",
    "supercharge",
    "harness",
    "ever-evolving",
)


@dataclass(frozen=True)
class PatternRule:
    code: str
    label: str
    expression: re.Pattern[str]


PATTERN_RULES = (
    PatternRule(
        "binary-contrast",
        "binary contrast",
        re.compile(
            r"\b(?:(?:(?:it|this)\s+is\s+not|(?:it|this)\s+isn['’]t"
            r"|it['’]s\s+not)[^.!?]{1,100}[,;—]\s*"
            r"(?:(?:it|this)\s+is|it['’]s)"
            r"|not\b[^.!?,;]{1,100}[,;]\s*but)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "throat-clearing",
        "throat-clearing opener",
        re.compile(
            r"(?:^|[.!?]\s+)(?:here['’]s\W+the\W+thing|let['’]s\W+be\W+honest"
            r"|the\W+truth\W+is|look)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "faux-insight",
        "faux-insight setup",
        re.compile(
            r"\b(?:what\W+most\W+people\W+get\W+wrong|what\W+nobody\W+tells\W+you"
            r"|the\W+secret\W+is|you\W+might\W+be\W+surprised)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule("colon-reveal", "colon reveal", re.compile(r":")),
    PatternRule(
        "importance-puffery",
        "importance puffery",
        re.compile(
            r"\b(?:this\W+is\W+important|this\W+matters\W+more\W+than\W+ever"
            r"|this\W+cannot\W+be\W+overstated|the\W+stakes\W+are\W+high)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "weasel-attribution",
        "weasel attribution",
        re.compile(
            r"\b(?:experts\W+say|research\W+shows|studies\W+suggest"
            r"|many\W+believe|it\W+is\W+widely\W+known)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "negative-listing",
        "negative listing",
        re.compile(
            r"(?:^|[.!?;]\s+)(?:no|not|without)\b[^.!?;]*"
            r"(?:[.!?;]\s+)(?:no|not|without)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "dramatic-fragmentation",
        "dramatic fragmentation",
        re.compile(
            r"(?:^|[.!?]\s+)(?:and|but)\b[^.!?]*[.!?]\s+(?:and|but)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "rhetorical-setup",
        "rhetorical setup",
        re.compile(
            r"\b(?:why\s*\?\s*because|the\W+result\s*\?|what\W+happens"
            r"\W+next\s*\?)",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "fake-profound-kicker",
        "fake-profound kicker",
        re.compile(
            r"\b(?:let\W+that\W+sink\W+in|read\W+that\W+again"
            r"|think\W+about\W+that|and\W+that\W+changes\W+everything)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        "summary-recap",
        "summary-recap ending",
        re.compile(
            r"\b(?:in\W+conclusion|to\W+sum\W+up|the\W+takeaway\W+is"
            r"|so\W+there\W+you\W+have\W+it)\b",
            re.IGNORECASE,
        ),
    ),
)

PAGE_REFERENCE_RE = re.compile(
    r"\b(?:as\W+)?(?:mentioned|shown|described|listed|noted)\W+"
    r"(?:above|below|earlier)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"(?<!\w)\d[\d,./:%$–—-]*")
SYMBOL_RE = re.compile(r"[$%&+=/@#]")
PARENTHETICAL_RE = re.compile(r"\([^)\n]+\)")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
BREAK_TAG_RE = re.compile(r"<break\b", re.IGNORECASE)
VISUAL_LAYOUT_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,6}\s+|[-*+•]\s+|\d+[.)]\s+)",
    re.MULTILINE,
)
MARKDOWN_BLOCK_RE = re.compile(r"^(?:#|>|[-*+]\s|\d+\.\s|\|)")


@dataclass(frozen=True)
class Segment:
    label: str
    text: str


@dataclass(frozen=True)
class NarrationInput:
    segments: tuple[Segment, ...]
    shows: tuple[tuple[int, dict[str, Any]], ...]
    mode: str
    enforce_writing_rules: bool

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)


@dataclass(frozen=True)
class Distribution:
    sentence_word_counts: tuple[int, ...]

    @property
    def sentence_count(self) -> int:
        return len(self.sentence_word_counts)

    @property
    def mean_words(self) -> float:
        if not self.sentence_word_counts:
            return 0.0
        return statistics.mean(self.sentence_word_counts)

    @property
    def stddev_words(self) -> float:
        if not self.sentence_word_counts:
            return 0.0
        return statistics.pstdev(self.sentence_word_counts)

    @property
    def long_sentence_count(self) -> int:
        return sum(count >= 20 for count in self.sentence_word_counts)

    @property
    def long_sentence_percent(self) -> float:
        return self._percent(self.long_sentence_count)

    @property
    def over_30_count(self) -> int:
        return sum(count > 30 for count in self.sentence_word_counts)

    @property
    def short_sentence_count(self) -> int:
        return sum(count <= 6 for count in self.sentence_word_counts)

    @property
    def short_sentence_percent(self) -> float:
        return self._percent(self.short_sentence_count)

    @property
    def longest_sentence(self) -> int:
        return max(self.sentence_word_counts, default=0)

    def metric(self, name: str) -> float:
        return float(getattr(self, name))

    def _percent(self, count: int) -> float:
        if not self.sentence_count:
            return 0.0
        return count * 100.0 / self.sentence_count


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    label: str | None = None
    source: str | None = None


class InputError(ValueError):
    """Raised when an input cannot provide valid narration."""


def analyze_distribution(text: str) -> Distribution:
    sentences = (
        sentence.strip()
        for sentence in SENTENCE_BOUNDARY_RE.split(text.strip())
        if sentence.strip()
    )
    counts = tuple(
        count
        for sentence in sentences
        if (count := len(WORD_RE.findall(sentence))) >= 3
    )
    return Distribution(counts)


def rhythm_diagnostics(distribution: Distribution) -> list[Diagnostic]:
    if not distribution.sentence_count:
        return [
            Diagnostic(
                "no-sentences",
                "no sentences with at least three words were found",
            )
        ]

    diagnostics = []
    for name, threshold in THRESHOLDS.items():
        actual = distribution.metric(name)
        failed = (
            actual < threshold.value
            if threshold.direction == "minimum"
            else actual > threshold.value
        )
        if failed:
            relation = "below" if threshold.direction == "minimum" else "above"
            diagnostics.append(
                Diagnostic(
                    f"rhythm-{name.replace('_', '-')}",
                    f"{threshold.label} is {format_metric(name, actual)}; "
                    f"{relation} the {threshold.direction} "
                    f"{format_metric(name, threshold.value)}",
                )
            )
    return diagnostics


def load_input(path: Path) -> NarrationInput:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error

    if path.suffix.lower() == ".json":
        return load_scenes(raw, path)
    if path.suffix.lower() == ".md":
        segments = markdown_prose_segments(raw)
        if not segments:
            raise InputError(f"{path} contains no prose paragraphs")
        return NarrationInput(
            segments=segments,
            shows=(),
            mode="Markdown calibration prose (rhythm only)",
            enforce_writing_rules=False,
        )

    segments = tuple(
        Segment(f"line {number}", line.strip())
        for number, line in enumerate(raw.splitlines(), start=1)
        if line.strip()
    )
    if not segments:
        raise InputError(f"{path} contains no narration")
    return NarrationInput(
        segments=segments,
        shows=(),
        mode="prose script",
        enforce_writing_rules=True,
    )


def load_scenes(raw: str, path: Path) -> NarrationInput:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise InputError(
            f"{path}:{error.lineno}:{error.colno}: invalid JSON: {error.msg}"
        ) from error

    if not isinstance(document, dict) or not isinstance(document.get("beats"), list):
        raise InputError(f"{path} must contain a top-level beats array")
    if not document["beats"]:
        raise InputError(f"{path} must contain at least one beat")

    segments = []
    shows = []
    for index, beat in enumerate(document["beats"], start=1):
        if not isinstance(beat, dict):
            raise InputError(f"{path}: beat {index} must be an object")
        say = beat.get("say")
        if not isinstance(say, str) or not say.strip():
            raise InputError(f"{path}: beat {index} must contain a non-empty say string")
        show = beat.get("show")
        if not isinstance(show, dict):
            raise InputError(f"{path}: beat {index} must contain a show object")
        segments.append(Segment(f"beat {index}", say.strip()))
        shows.append((index, show))

    return NarrationInput(
        segments=tuple(segments),
        shows=tuple(shows),
        mode="scenes.json narration",
        enforce_writing_rules=True,
    )


def markdown_prose_segments(raw: str) -> tuple[Segment, ...]:
    segments = []
    block_lines: list[str] = []
    block_start = 0
    in_fence = False

    def flush() -> None:
        nonlocal block_lines, block_start
        if block_lines:
            first = block_lines[0].lstrip()
            if not MARKDOWN_BLOCK_RE.match(first):
                segments.append(
                    Segment(
                        f"line {block_start}",
                        " ".join(line.strip() for line in block_lines),
                    )
                )
        block_lines = []
        block_start = 0

    for number, line in enumerate(raw.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
            continue
        if not block_lines:
            block_start = number
        block_lines.append(line)
    flush()
    return tuple(segments)


def writing_diagnostics(narration: NarrationInput) -> list[Diagnostic]:
    text, spans = joined_text_with_spans(narration.segments)
    diagnostics: list[Diagnostic] = []

    for term in BANNED_TERMS:
        expression = phrase_expression(term)
        for match in expression.finditer(text):
            segment = segment_at(match.start(), spans)
            diagnostics.append(
                Diagnostic(
                    "banned-word",
                    f'banned word or phrase "{term}"',
                    segment.label,
                    segment.text,
                )
            )

    for rule in PATTERN_RULES:
        for match in rule.expression.finditer(text):
            segment = segment_at(match.end() - 1, spans)
            diagnostics.append(
                Diagnostic(
                    rule.code,
                    rule.label,
                    segment.label,
                    segment.text,
                )
            )

    spoken_checks: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        ("written-number", "write numbers as they should be spoken", NUMBER_RE),
        ("spoken-symbol", "write symbols as they should be spoken", SYMBOL_RE),
        (
            "parenthetical",
            "rewrite parenthetical text for a forward-only listen",
            PARENTHETICAL_RE,
        ),
        ("page-reference", "remove page-position references", PAGE_REFERENCE_RE),
        ("acronym", "expand and spell the pronunciation of acronyms", ACRONYM_RE),
        ("break-tag", "shape pacing with sentences, not break tags", BREAK_TAG_RE),
        (
            "visual-layout",
            "move headings, bullets, and fragment lists into the visual",
            VISUAL_LAYOUT_RE,
        ),
    )
    for code, message, expression in spoken_checks:
        for match in expression.finditer(text):
            segment = segment_at(match.start(), spans)
            diagnostics.append(
                Diagnostic(code, message, segment.label, segment.text)
            )

    return diagnostics


def duplicate_visual_diagnostics(
    shows: Iterable[tuple[int, dict[str, Any]]],
) -> list[Diagnostic]:
    first_use: dict[tuple[str, str], int] = {}
    diagnostics = []
    for beat_number, show in shows:
        identity = visual_identity(show)
        if identity in first_use:
            diagnostics.append(
                Diagnostic(
                    "duplicate-visual",
                    f"visual repeats beat {first_use[identity]}",
                    f"beat {beat_number}",
                    visual_description(show),
                )
            )
        else:
            first_use[identity] = beat_number
    return diagnostics


def visual_identity(show: dict[str, Any]) -> tuple[str, str]:
    path = show.get("path")
    if isinstance(path, str) and path.strip():
        return ("path", path.strip())
    lines = show.get("lines")
    if isinstance(lines, list):
        return ("lines", json.dumps(lines, ensure_ascii=False, sort_keys=True))
    return ("show", json.dumps(show, ensure_ascii=False, sort_keys=True))


def visual_description(show: dict[str, Any]) -> str:
    if isinstance(show.get("path"), str):
        return show["path"]
    if isinstance(show.get("lines"), list):
        return " | ".join(str(line) for line in show["lines"])
    return json.dumps(show, ensure_ascii=False, sort_keys=True)


def joined_text_with_spans(
    segments: tuple[Segment, ...],
) -> tuple[str, tuple[tuple[int, int, Segment], ...]]:
    chunks = []
    spans = []
    offset = 0
    for segment in segments:
        if chunks:
            chunks.append("\n")
            offset += 1
        start = offset
        chunks.append(segment.text)
        offset += len(segment.text)
        spans.append((start, offset, segment))
    return "".join(chunks), tuple(spans)


def segment_at(
    offset: int, spans: tuple[tuple[int, int, Segment], ...]
) -> Segment:
    for start, end, segment in spans:
        if offset < start:
            return segment
        if start <= offset < end:
            return segment
    return spans[-1][2]


def phrase_expression(phrase: str) -> re.Pattern[str]:
    words = re.findall(r"\w+", phrase)
    return re.compile(
        rf"\b{r'[\W_]+'.join(re.escape(word) for word in words)}\b",
        re.IGNORECASE,
    )


def format_metric(name: str, value: float) -> str:
    if name in {"over_30_count"}:
        return str(int(value))
    if name in {"long_sentence_percent", "short_sentence_percent"}:
        return f"{value:.1f}%"
    return f"{value:.2f}"


def print_report(path: Path, mode: str, distribution: Distribution) -> None:
    print(f"Lint report: {path}")
    print(f"Mode: {mode}")
    print(f"Sentences analyzed: {distribution.sentence_count}")
    print(
        f"Mean sentence length: {distribution.mean_words:.2f} words "
        f"(minimum {THRESHOLDS['mean_words'].value:.2f})"
    )
    print(
        f"Sentence-length standard deviation: {distribution.stddev_words:.2f} "
        f"(minimum {THRESHOLDS['stddev_words'].value:.2f})"
    )
    print(
        f"Sentences with at least 20 words: {distribution.long_sentence_count}/"
        f"{distribution.sentence_count} ({distribution.long_sentence_percent:.1f}%; "
        f"minimum {THRESHOLDS['long_sentence_percent'].value:.1f}%)"
    )
    print(
        f"Longest sentence: {distribution.longest_sentence} words "
        f"({distribution.over_30_count} over 30; "
        f"minimum {int(THRESHOLDS['over_30_count'].value)})"
    )
    print(
        f"Sentences with at most 6 words: {distribution.short_sentence_count}/"
        f"{distribution.sentence_count} ({distribution.short_sentence_percent:.1f}%; "
        f"maximum {THRESHOLDS['short_sentence_percent'].value:.1f}%)"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint a prose narration script or scenes.json before storyboard."
    )
    parser.add_argument("script", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        narration = load_input(args.script)
    except InputError as error:
        print(f"lint error: {error}", file=sys.stderr)
        return 2

    distribution = analyze_distribution(narration.text)
    diagnostics = rhythm_diagnostics(distribution)
    if narration.enforce_writing_rules:
        diagnostics.extend(writing_diagnostics(narration))
    diagnostics.extend(duplicate_visual_diagnostics(narration.shows))

    print_report(args.script, narration.mode, distribution)
    if diagnostics:
        print(f"\nLint failed with {len(diagnostics)} issue(s):")
        for diagnostic in diagnostics:
            location = f" at {diagnostic.label}" if diagnostic.label else ""
            print(f"- [{diagnostic.code}]{location}: {diagnostic.message}")
            if diagnostic.source:
                print(f"    {diagnostic.source}")
        return 1

    print("\nLint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
