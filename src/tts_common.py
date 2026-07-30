#!/usr/bin/env python3
"""Shared transcript, dialogue timing, and audio-stitching helpers."""

from __future__ import annotations

import subprocess
from typing import Any


class ScriptFormatError(ValueError):
    """Raised when a script cannot produce a valid voice track."""


def build_transcript(beats: list[dict[str, Any]]) -> tuple[str, list[tuple[int, int]]]:
    """Join beats for one continuous read and retain each character span."""
    full = ""
    spans: list[tuple[int, int]] = []
    for index, beat in enumerate(beats):
        say = beat["say"].strip()
        if index:
            full += "\n"
        start = len(full)
        full += say
        spans.append((start, len(full)))
    return full, spans


def is_dialogue(document: dict[str, Any]) -> bool:
    """Only the explicit dialogue format changes legacy narrator behavior."""
    return document.get("format") == "dialogue"


def validate_dialogue(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the two-host schema independently of a particular TTS engine."""
    speakers = document.get("speakers")
    if not isinstance(speakers, dict) or len(speakers) != 2:
        raise ScriptFormatError("dialogue requires exactly two configured speakers")
    if any(not isinstance(name, str) or not name.strip() for name in speakers):
        raise ScriptFormatError("dialogue speaker names must be non-empty strings")
    if any(not isinstance(config, dict) for config in speakers.values()):
        raise ScriptFormatError("each dialogue speaker must have a configuration object")

    beats = document.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ScriptFormatError("dialogue requires at least one beat")
    used: set[str] = set()
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            raise ScriptFormatError(f"beat {index} must be an object")
        speaker = beat.get("speaker")
        if not isinstance(speaker, str) or speaker not in speakers:
            raise ScriptFormatError(
                f"beat {index} speaker must name one of: {', '.join(speakers)}"
            )
        used.add(speaker)
    missing = [name for name in speakers if name not in used]
    if missing:
        raise ScriptFormatError(
            f"dialogue must include a turn for every speaker; missing: {', '.join(missing)}"
        )
    return speakers


def build_dialogue_groups(
    document: dict[str, Any], voice_field: str
) -> dict[str, dict[str, Any]]:
    """Group all turns by speaker so each voice is synthesized exactly once."""
    speakers = validate_dialogue(document)
    groups: dict[str, dict[str, Any]] = {}
    voices: list[str] = []
    for name, config in speakers.items():
        voice = config.get(voice_field)
        if not isinstance(voice, str) or not voice.strip():
            raise ScriptFormatError(
                f'dialogue speaker "{name}" requires a non-empty {voice_field}'
            )
        voice = voice.strip()
        groups[name] = {"voice": voice, "beats": [], "beat_indices": []}
        voices.append(voice)
    if len(set(voices)) != len(voices):
        raise ScriptFormatError(
            f"dialogue speakers must use distinct {voice_field} values"
        )

    for beat_index, beat in enumerate(document["beats"]):
        group = groups[beat["speaker"]]
        group["beats"].append(beat)
        group["beat_indices"].append(beat_index)
    for group in groups.values():
        group["text"], group["spans"] = build_transcript(group["beats"])
    return groups


def approximate_track(
    text: str, spans: list[tuple[int, int]], duration: float
) -> dict[str, Any]:
    """Approximate a synthesized track from transcript character positions."""
    import re

    scale = duration / len(text) if text else 0.0
    turns = [
        {"audio_start": start * scale, "audio_end": end * scale}
        for start, end in spans
    ]
    words = []
    for match in re.finditer(r"\S+", text):
        words.append(
            {
                "w": match.group().strip(".,!?;:"),
                "start": match.start() * scale,
                "end": match.end() * scale,
                "_char_start": match.start(),
                "_char_end": match.end(),
            }
        )
    return {"duration": duration, "turns": turns, "words": words}


def alignment_track(
    text: str,
    spans: list[tuple[int, int]],
    alignment: dict[str, Any],
) -> dict[str, Any]:
    """Build turn and word timing from a character-aligned TTS response."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        raise ScriptFormatError("TTS alignment arrays have different lengths")
    duration = float(ends[-1]) if ends else 0.0
    turns = []
    for start, end in spans:
        clipped_end = min(end, len(chars))
        turns.append(
            {
                "audio_start": float(starts[start]) if start < len(starts) else 0.0,
                "audio_end": (
                    float(ends[clipped_end - 1])
                    if 0 < clipped_end <= len(ends)
                    else duration
                ),
            }
        )

    words: list[dict[str, Any]] = []
    current = ""
    word_start_time = None
    word_end_time = None
    word_start_char = None
    for position, (character, start, end) in enumerate(zip(chars, starts, ends)):
        if character.isspace():
            if current:
                words.append(
                    {
                        "w": current,
                        "start": float(word_start_time),
                        "end": float(word_end_time),
                        "_char_start": word_start_char,
                        "_char_end": position,
                    }
                )
                current = ""
                word_start_time = word_end_time = word_start_char = None
        else:
            if not current:
                word_start_time = start
                word_start_char = position
            current += character
            word_end_time = end
    if current:
        words.append(
            {
                "w": current,
                "start": float(word_start_time),
                "end": float(word_end_time),
                "_char_start": word_start_char,
                "_char_end": len(chars),
            }
        )
    return {"duration": duration, "turns": turns, "words": words}


def _clean_word(word: dict[str, Any], offset: float = 0.0) -> dict[str, Any]:
    return {
        "w": word["w"],
        "start": round(word["start"] + offset, 3),
        "end": round(word["end"] + offset, 3),
    }


def narrator_outputs(track: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert one continuous track to the public output contract."""
    words = [_clean_word(word) for word in track["words"]]
    timing = {
        "duration": round(track["duration"], 3),
        "beats": [
            {
                "audio_start": round(turn["audio_start"], 3),
                "audio_end": round(turn["audio_end"], 3),
            }
            for turn in track["turns"]
        ],
    }
    return words, timing


def turn_windows(turns: list[dict[str, float]], duration: float) -> list[tuple[float, float]]:
    """Partition one speaker track without dropping its natural between-turn pauses."""
    if not turns:
        return []
    boundaries = [0.0]
    for previous, following in zip(turns, turns[1:]):
        boundaries.append((previous["audio_end"] + following["audio_start"]) / 2.0)
    boundaries.append(duration)
    return list(zip(boundaries, boundaries[1:]))


def interleave_dialogue(
    beats: list[dict[str, Any]],
    groups: dict[str, dict[str, Any]],
    tracks: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Reorder speaker-track turns into conversation order and shift all timestamps."""
    by_beat: dict[int, dict[str, Any]] = {}
    for speaker, group in groups.items():
        track = tracks[speaker]
        windows = turn_windows(track["turns"], track["duration"])
        for local_index, (beat_index, span, window) in enumerate(
            zip(group["beat_indices"], group["spans"], windows)
        ):
            by_beat[beat_index] = {
                "speaker": speaker,
                "span": span,
                "window": window,
                "turn": track["turns"][local_index],
                "words": [
                    word
                    for word in track["words"]
                    if span[0] <= word["_char_start"] < span[1]
                ],
            }

    words: list[dict[str, Any]] = []
    timing = {"duration": 0.0, "beats": []}
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for beat_index in range(len(beats)):
        item = by_beat[beat_index]
        segment_start, segment_end = item["window"]
        offset = cursor - segment_start
        words.extend(_clean_word(word, offset) for word in item["words"])
        timing["beats"].append(
            {
                "audio_start": round(item["turn"]["audio_start"] + offset, 3),
                "audio_end": round(item["turn"]["audio_end"] + offset, 3),
            }
        )
        segments.append(
            {
                "speaker": item["speaker"],
                "start": segment_start,
                "end": segment_end,
            }
        )
        cursor += segment_end - segment_start
    timing["duration"] = round(cursor, 3)
    return words, timing, segments


def stitch_audio(
    source_paths: dict[str, str], segments: list[dict[str, Any]], output_path: str
) -> None:
    """Concatenate turn slices as a mono MP3, preserving conversation order."""
    input_index = {speaker: index for index, speaker in enumerate(source_paths)}
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for path in source_paths.values():
        command.extend(("-i", path))

    filters = []
    labels = []
    for index, segment in enumerate(segments):
        if segment["end"] <= segment["start"]:
            raise ScriptFormatError("dialogue produced an empty audio turn")
        label = f"turn{index}"
        source = input_index[segment["speaker"]]
        filters.append(
            f"[{source}:a]atrim=start={segment['start']:.6f}:end={segment['end']:.6f},"
            f"asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=mono[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    command.extend(
        (
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ac",
            "1",
            output_path,
        )
    )
    subprocess.run(command, check=True)
