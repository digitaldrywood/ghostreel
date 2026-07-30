#!/usr/bin/env python3
"""Derive storyboard beats from an approved Markdown narration script."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from prose_script import ProseFormatError, parse_prose


FUZZY_MATCH_MINIMUM = 0.65


class SegmentationError(ValueError):
    """Raised when prose or an existing storyboard cannot be segmented safely."""


@dataclass(frozen=True)
class SegmentationResult:
    document: dict[str, Any]
    preserved: int
    placeholders: int
    dropped_cues: int


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SegmentationError(f"cannot read existing storyboard {path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("beats"), list):
        raise SegmentationError(f"{path} must contain a top-level beats array")
    for index, beat in enumerate(document["beats"], start=1):
        if not isinstance(beat, dict):
            raise SegmentationError(f"{path}: beat {index} must be an object")
        if not isinstance(beat.get("say"), str) or not beat["say"].strip():
            raise SegmentationError(f"{path}: beat {index} must contain a non-empty say")
        if not isinstance(beat.get("show"), dict):
            raise SegmentationError(f"{path}: beat {index} must contain a show object")
    return document


def match_beats(paragraphs: tuple[str, ...], beats: list[dict[str, Any]]) -> dict[int, int]:
    """Match new paragraphs to old beats without relying only on position."""

    new_text = [normalize(paragraph) for paragraph in paragraphs]
    old_text = [normalize(beat["say"]) for beat in beats]
    matches: dict[int, int] = {}
    unused_old = set(range(len(beats)))

    # Exact text survives insertions, deletions, and reordering.
    for new_index, text in enumerate(new_text):
        candidates = [index for index in unused_old if old_text[index] == text]
        if candidates:
            old_index = min(candidates, key=lambda index: abs(index - new_index))
            matches[new_index] = old_index
            unused_old.remove(old_index)

    # Close edits keep their visual, but substantially replaced thoughts do not.
    for new_index, text in enumerate(new_text):
        if new_index in matches or not unused_old:
            continue
        candidates = [
            (
                SequenceMatcher(None, text, old_text[old_index], autojunk=False).ratio(),
                -abs(old_index - new_index),
                -old_index,
                old_index,
            )
            for old_index in unused_old
        ]
        score, _, _, old_index = max(candidates)
        if score >= FUZZY_MATCH_MINIMUM:
            matches[new_index] = old_index
            unused_old.remove(old_index)

    return matches


def placeholder_show(index: int) -> dict[str, Any]:
    return {"type": "text", "lines": ["ASSIGN VISUAL", f"BEAT {index:02d}"]}


def is_placeholder(show: dict[str, Any]) -> bool:
    lines = show.get("lines")
    return (
        show.get("type") == "text"
        and isinstance(lines, list)
        and len(lines) == 2
        and lines[0] == "ASSIGN VISUAL"
        and isinstance(lines[1], str)
        and lines[1].startswith("BEAT ")
    )


def visual_identity(show: dict[str, Any]) -> tuple[str, str]:
    path = show.get("path")
    if isinstance(path, str) and path.strip():
        return ("path", path.strip())
    lines = show.get("lines")
    if isinstance(lines, list):
        return ("lines", json.dumps(lines, ensure_ascii=False, sort_keys=True))
    return ("show", json.dumps(show, ensure_ascii=False, sort_keys=True))


def require_unique_visuals(beats: list[dict[str, Any]]) -> None:
    first_use: dict[tuple[str, str], int] = {}
    for index, beat in enumerate(beats, start=1):
        identity = visual_identity(beat["show"])
        if identity in first_use:
            raise SegmentationError(
                f"visual assigned to beat {index} repeats beat {first_use[identity]}"
            )
        first_use[identity] = index


def segment(raw: str, existing: dict[str, Any] | None = None) -> SegmentationResult:
    try:
        parsed = parse_prose(raw)
    except ProseFormatError as error:
        raise SegmentationError(str(error)) from error

    tagged = [paragraph.speaker is not None for paragraph in parsed]
    if any(tagged) and not all(tagged):
        raise SegmentationError(
            "dialogue prose must tag every paragraph with [speaker]"
        )
    dialogue = bool(tagged and all(tagged))
    speaker_names = tuple(
        dict.fromkeys(
            paragraph.speaker for paragraph in parsed if paragraph.speaker
        )
    )
    if dialogue and len(speaker_names) != 2:
        raise SegmentationError("dialogue prose must use exactly two speaker tags")
    if existing and existing.get("format") == "dialogue" and not dialogue:
        raise SegmentationError(
            "dialogue scenes require [speaker] on every prose paragraph"
        )
    if dialogue and existing and isinstance(existing.get("speakers"), dict):
        configured = set(existing["speakers"])
        if configured != set(speaker_names):
            raise SegmentationError(
                "dialogue prose speaker tags must match the configured speakers"
            )

    paragraphs = tuple(paragraph.text for paragraph in parsed)
    old_beats = list(existing.get("beats", [])) if existing else []
    matches = match_beats(paragraphs, old_beats)
    beats: list[dict[str, Any]] = []
    dropped_cues = 0

    for index, paragraph in enumerate(paragraphs, start=1):
        old_index = matches.get(index - 1)
        if old_index is None:
            beat: dict[str, Any] = {"show": placeholder_show(index)}
        else:
            beat = dict(old_beats[old_index])
            if is_placeholder(beat["show"]):
                beat["show"] = placeholder_show(index)
            cue = beat.get("cue")
            if isinstance(cue, str) and cue not in paragraph:
                beat.pop("cue")
                dropped_cues += 1
        beat["say"] = paragraph
        if dialogue:
            beat["speaker"] = parsed[index - 1].speaker
        else:
            beat.pop("speaker", None)
        # Keep the public schema easy to scan: narration, speaker, cue, then show.
        ordered = {"say": beat.pop("say")}
        if "speaker" in beat:
            ordered["speaker"] = beat.pop("speaker")
        if "cue" in beat:
            ordered["cue"] = beat.pop("cue")
        ordered.update(beat)
        beats.append(ordered)

    require_unique_visuals(beats)
    if existing:
        document = {key: value for key, value in existing.items() if key != "beats"}
        if dialogue:
            document["format"] = "dialogue"
            document.pop("voice_id", None)
            if not isinstance(document.get("speakers"), dict):
                document["speakers"] = {
                    name: {"local_voice": "", "voice_id": ""}
                    for name in speaker_names
                }
    else:
        if dialogue:
            document = {
                "format": "dialogue",
                "aspect": "16:9",
                "speakers": {
                    name: {"local_voice": "", "voice_id": ""}
                    for name in speaker_names
                },
            }
        else:
            document = {"format": "narrator", "aspect": "16:9", "voice_id": ""}
    document["beats"] = beats
    return SegmentationResult(
        document=document,
        preserved=len(matches),
        placeholders=sum(is_placeholder(beat["show"]) for beat in beats),
        dropped_cues=dropped_cues,
    )


def write_document(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Turn approved Markdown prose into scenes.json storyboard beats."
    )
    parser.add_argument("script", type=Path, help="plain Markdown narration")
    parser.add_argument(
        "scenes",
        type=Path,
        help="scenes.json to create or update while preserving matched assignments",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw = args.script.read_text(encoding="utf-8")
        existing = load_existing(args.scenes)
        result = segment(raw, existing)
        if existing != result.document:
            write_document(args.scenes, result.document)
    except (OSError, SegmentationError) as error:
        print(f"segment error: {error}", file=sys.stderr)
        return 2

    print(
        f"Segmented {len(result.document['beats'])} paragraph(s) -> {args.scenes} "
        f"(preserved {result.preserved}, placeholders {result.placeholders}, "
        f"dropped cues {result.dropped_cues})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
