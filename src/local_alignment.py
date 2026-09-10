"""Conservative, offline word alignment for destructive local dialogue edits."""

import math
import os
import re

from tts_common import ScriptFormatError


def load_aligner():
    """Load only an explicitly installed model; never download during a render."""
    path = os.environ.get("GHOSTREEL_ALIGN_MODEL", "")
    if not os.path.isdir(path):
        raise ScriptFormatError(
            "local dialogue requires GHOSTREEL_ALIGN_MODEL pointing to a local "
            "faster-whisper model directory; see README.md dialogue alignment setup"
        )
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(path, device="cpu", compute_type="int8", local_files_only=True)
    except Exception as error:
        raise ScriptFormatError(
            "cannot load local dialogue aligner; install faster-whisper in the "
            "Kokoro Python environment and check GHOSTREEL_ALIGN_MODEL: " + str(error)
        ) from error


def normalized(word):
    return "".join(character for character in word.casefold() if character.isalnum())


def aligned_track(text, spans, duration, recognized, silences):
    """Associate every recognized word with the transcript and validate quiet cuts."""
    expected = list(re.finditer(r"\S+", text))
    recognized = [word for word in recognized if normalized(word["word"])]
    if ([normalized(match.group()) for match in expected]
            != [normalized(word["word"]) for word in recognized]):
        raise ScriptFormatError(
            "local dialogue alignment does not match the complete speaker transcript; "
            "check pronunciation or use a more accurate local alignment model"
        )
    words = []
    previous_end = 0.0
    for match, word in zip(expected, recognized):
        start, end = float(word["start"]), float(word["end"])
        if not (math.isfinite(start) and math.isfinite(end)
                and previous_end <= start < end <= duration):
            raise ScriptFormatError("local dialogue alignment has invalid or overlapping word times")
        words.append({"w": match.group().strip(".,!?;:"), "start": start, "end": end,
                      "_char_start": match.start(), "_char_end": match.end()})
        previous_end = end
    turns = []
    for start, end in spans:
        selected = [word for word in words if start <= word["_char_start"] < end]
        if not selected:
            raise ScriptFormatError("local dialogue alignment contains an empty turn")
        turns.append({"audio_start": selected[0]["start"], "audio_end": selected[-1]["end"]})
    # Choose only a quiet span inside the transcript-associated gap. Do not use
    # proportional timing or an unrelated nearby pause as a fallback.
    cuts = [0.0]
    for index, (previous, following) in enumerate(zip(turns, turns[1:]), 1):
        candidates = [(max(previous["audio_end"], silence["start"]),
                       min(following["audio_start"], silence["end"]))
                      for silence in silences]
        candidates = [(start, end) for start, end in candidates if end - start >= 0.04]
        if len(candidates) != 1:
            raise ScriptFormatError(
                f"local dialogue turn {index}: cannot identify one safe quiet boundary; "
                "check pronunciation/pacing or use a more accurate local alignment model"
            )
        start, end = candidates[0]
        cuts.append((start + end) / 2)
    cuts.append(duration)
    return {"duration": duration, "turns": turns, "words": words,
            "windows": list(zip(cuts, cuts[1:]))}


def align_audio(model, path, text, spans, duration, silences):
    try:
        segments, _ = model.transcribe(path, word_timestamps=True, vad_filter=False)
        recognized = [{"word": word.word, "start": word.start, "end": word.end}
                      for segment in segments for word in (segment.words or [])]
        return aligned_track(text, spans, duration, recognized, silences)
    except ScriptFormatError:
        raise
    except Exception as error:
        raise ScriptFormatError(f"local dialogue audio alignment failed: {error}") from error
