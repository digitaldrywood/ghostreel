#!/usr/bin/env python3
"""tts_local.py — FREE local voiceover for rough cuts. $0, no API.

Build the WHOLE video with a local voice first. Watch it end to end: does the script
breathe, do the screen-to-screen cuts land? Re-edit for nothing. Only when it's right
do you pay for the real voice (src/tts.py). This is the single biggest cost-saver.

Engines (SCRATCH_ENGINE env, default "kokoro"):
    kokoro  — Kokoro-82M via kokoro-onnx. Near-human quality, ~5x faster than
              realtime on CPU. Lives OUTSIDE the repo on purpose (~350MB of model
              files that don't belong in git or synced folders):
                  mkdir -p ~/.local/share/kokoro-tts && cd ~/.local/share/kokoro-tts
                  python3 -m venv venv && venv/bin/pip install kokoro-onnx soundfile
                  # download kokoro-v1.0.onnx + voices-v1.0.bin from:
                  # https://github.com/thewh1teagle/kokoro-onnx/releases
              Env: KOKORO_DIR (default ~/.local/share/kokoro-tts),
                   KOKORO_VOICE (default am_michael), KOKORO_SPEED (default 1.0)
    piper   — legacy fallback. Robotic but dependable, tiny install.
              pip install piper-tts, then set PIPER_BIN + PIPER_VOICE=/path/to/voice.onnx

Falls back to piper automatically when the kokoro model files are missing.
Kokoro weights are Apache-2.0 and kokoro-onnx is MIT, so both are fine to use here.

Usage: python3 src/tts_local.py --preflight <script.json>
       python3 src/tts_local.py <script.json> <run_dir>
Writes the same files as tts.py (vo.mp3, words.json, timing.json) so the rest of the
pipeline is identical. Word timings are approximate (spread across the continuous
transcript) — fine for reviewing flow; the paid pass gets exact alignment.
"""
import json, os, re, shutil, subprocess, sys, tempfile

from tts_common import (
    ScriptFormatError,
    approximate_track,
    build_dialogue_groups,
    build_transcript,
    interleave_dialogue,
    is_dialogue,
    narrator_outputs,
    stitch_audio,
)
from voices import voice_details

KOKORO_DIR = os.environ.get("KOKORO_DIR", os.path.expanduser("~/.local/share/kokoro-tts"))
KOKORO_PY = os.path.join(KOKORO_DIR, "venv/bin/python")
KOKORO_MODEL = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
KOKORO_VOICES = os.path.join(KOKORO_DIR, "voices-v1.0.bin")

# Keep clause pauses quick, let sentences settle, and give a new visual/topic room to
# breathe. These values are applied only inside silence the synthesizer already made.
PAUSE_SECONDS = {"clause": 0.10, "sentence": 0.21, "beat": 0.66}
SILENCE_THRESHOLD = 0.04


def approximate_timings(text, spans, duration):
    """Map transcript character positions onto the continuous audio duration."""
    return narrator_outputs(approximate_track(text, spans, duration))


def pause_boundaries(text, spans):
    """Return authored punctuation and beat boundaries in transcript order."""
    boundaries = []
    for beat_index, (start, end) in enumerate(spans):
        say = text[start:end]
        for match in re.finditer(r"[,;:](?=\s)|[.!?]+(?=[\"']?\s)", say):
            kind = "clause" if match.group()[0] in ",;:" else "sentence"
            boundaries.append({
                "position": start + match.end(),
                "kind": kind,
                "seconds": PAUSE_SECONDS[kind],
            })
        if beat_index < len(spans) - 1:
            boundaries.append({
                "position": end,
                "kind": "beat",
                "seconds": PAUSE_SECONDS["beat"],
            })
    return boundaries


def detect_silences(path):
    """Find quiet spans in a synthesized WAV using the same threshold as validation."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
         f"silencedetect=noise=-40dB:d={SILENCE_THRESHOLD}", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True,
    )
    starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", result.stderr)]
    ends = [
        (float(end), float(length))
        for end, length in re.findall(
            r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", result.stderr
        )
    ]
    return [
        {"start": start, "end": end, "duration": length}
        for start, (end, length) in zip(starts, ends)
    ]


def match_pauses(boundaries, silences, text_length, duration):
    """Match each text boundary to the longest nearby natural pause.

    Character position is already the local rough path's timing approximation. Midpoints
    between adjacent authored boundaries give each boundary a disjoint audio window, and
    choosing the longest quiet span avoids mistaking a normal inter-word gap for a pause.
    """
    if not boundaries or not silences or not text_length or not duration:
        return []
    expected = [boundary["position"] / text_length * duration for boundary in boundaries]
    matches = []
    for index, (boundary, at) in enumerate(zip(boundaries, expected)):
        previous = expected[index - 1] if index else 0.0
        following = expected[index + 1] if index + 1 < len(expected) else duration
        lower, upper = (previous + at) / 2, (at + following) / 2
        candidates = [
            silence for silence in silences
            if silence["duration"] >= SILENCE_THRESHOLD
            and lower <= (silence["start"] + silence["end"]) / 2 < upper
        ]
        if candidates:
            matches.append((boundary, max(candidates, key=lambda item: item["duration"])))
    return matches


def sample_rate(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate", "-of", "default=nk=1:nw=1", path],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def shape_pauses(path, text, spans):
    """Resize existing silent spans by boundary type without another synthesis call."""
    duration = dur(path)
    boundaries = pause_boundaries(text, spans)
    matches = match_pauses(boundaries, detect_silences(path), len(text), duration)
    if not matches:
        print("ROUGH PAUSES -> no authored boundaries matched natural silence", file=sys.stderr)
        return []

    filters, inputs, cursor = [], [], 0.0
    rate = sample_rate(path)
    for index, (boundary, silence) in enumerate(matches):
        audio_label, silence_label = f"a{index}", f"s{index}"
        filters.append(
            f"[0:a]atrim=start={cursor:.6f}:end={silence['start']:.6f},"
            f"asetpts=PTS-STARTPTS[{audio_label}]"
        )
        filters.append(
            f"anullsrc=r={rate}:cl=mono:d={boundary['seconds']:.3f}"
            f"[{silence_label}]"
        )
        inputs.extend((f"[{audio_label}]", f"[{silence_label}]"))
        cursor = silence["end"]

    tail_label = f"a{len(matches)}"
    filters.append(f"[0:a]atrim=start={cursor:.6f},asetpts=PTS-STARTPTS[{tail_label}]")
    inputs.append(f"[{tail_label}]")
    filters.append(f"{''.join(inputs)}concat=n={len(inputs)}:v=0:a=1[out]")

    shaped = f"{path}.shaped.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-filter_complex",
         ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", shaped],
        check=True,
    )
    os.replace(shaped, path)

    totals = {kind: [0, 0] for kind in PAUSE_SECONDS}
    for boundary in boundaries:
        totals[boundary["kind"]][1] += 1
    for boundary, _ in matches:
        totals[boundary["kind"]][0] += 1
    summary = " ".join(
        f"{kind}={matched}/{authored}@{PAUSE_SECONDS[kind]:.2f}s"
        for kind, (matched, authored) in totals.items() if authored
    )
    print(f"ROUGH PAUSES -> {summary}", file=sys.stderr)
    return matches


def missing_kokoro_artifacts():
    """Return the required Kokoro artifacts that are not installed."""
    required = (
        ("Python interpreter", KOKORO_PY),
        ("ONNX model", KOKORO_MODEL),
        ("voices bundle", KOKORO_VOICES),
    )
    return [(name, path) for name, path in required if not os.path.isfile(path)]


def pick_engine(dialogue=False):
    eng = os.environ.get("SCRATCH_ENGINE", "kokoro")
    if eng not in {"kokoro", "piper"}:
        sys.exit(
            f"error: unsupported SCRATCH_ENGINE {eng!r}; expected 'kokoro' or 'piper'"
        )
    missing = missing_kokoro_artifacts() if eng == "kokoro" else []
    if missing:
        details = ", ".join(f"{name}: {path}" for name, path in missing)
        if dialogue:
            sys.exit(
                "error: dialogue rough cuts require Kokoro for two local voices; "
                f"missing {details}. Piper cannot provide two voices"
            )
        print(f"kokoro unavailable; missing {details} — falling back to piper",
              file=sys.stderr)
        eng = "piper"
    return eng


def validate_kokoro_voice(voice):
    """Validate a configured voice without loading the Kokoro model."""
    try:
        voice_details(voice)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    return voice


def validate_kokoro_runtime(selected_voices):
    """Verify that Kokoro loads and the installed bundle contains each voice."""
    if not os.access(KOKORO_PY, os.X_OK):
        sys.exit(f"error: Kokoro Python interpreter is not executable: {KOKORO_PY}")
    probe = """
import sys

try:
    import soundfile
    from kokoro_onnx import Kokoro
except Exception as error:
    print(f"IMPORT_ERROR={type(error).__name__}: {error}", file=sys.stderr)
    raise SystemExit(3)

try:
    engine = Kokoro(sys.argv[1], sys.argv[2])
except Exception as error:
    print(f"LOAD_ERROR={type(error).__name__}: {error}", file=sys.stderr)
    raise SystemExit(1)

missing = [voice for voice in sys.argv[3:] if voice not in engine.voices]
if missing:
    print("MISSING_VOICES=" + ",".join(missing))
    raise SystemExit(2)
"""
    result = subprocess.run(
        [
            KOKORO_PY,
            "-c",
            probe,
            KOKORO_MODEL,
            KOKORO_VOICES,
            *selected_voices,
        ],
        capture_output=True,
        text=True,
    )
    missing = next(
        (
            line.removeprefix("MISSING_VOICES=")
            for line in result.stdout.splitlines()
            if line.startswith("MISSING_VOICES=")
        ),
        None,
    )
    if missing is not None:
        sys.exit(
            f"error: Kokoro voices bundle {KOKORO_VOICES} does not contain selected "
            f"voice(s): {missing}"
        )
    import_error = next(
        (
            line.removeprefix("IMPORT_ERROR=")
            for line in result.stderr.splitlines()
            if line.startswith("IMPORT_ERROR=")
        ),
        None,
    )
    if import_error is not None:
        sys.exit(
            f"error: Kokoro Python environment {KOKORO_PY} cannot import required "
            f"runtime dependencies: {import_error}"
        )
    if result.returncode:
        detail = next(
            (
                line.removeprefix("LOAD_ERROR=")
                for line in result.stderr.splitlines()
                if line.startswith("LOAD_ERROR=")
            ),
            "runtime probe failed",
        )
        sys.exit(
            f"error: Kokoro model or voices bundle is unusable ({KOKORO_MODEL}, "
            f"{KOKORO_VOICES}): {detail}"
        )


def resolve_piper():
    """Return a usable Piper executable and voice model or exit with specifics."""
    configured = os.environ.get("PIPER_BIN")
    piper = shutil.which(configured or "piper")
    if not piper:
        detail = f": {configured}" if configured else ""
        sys.exit(
            "error: no usable Piper executable found; install piper-tts or set "
            f"PIPER_BIN to an executable{detail}"
        )
    voice = os.environ.get("PIPER_VOICE")
    if not voice:
        sys.exit("error: PIPER_VOICE is not set; point it to a Piper .onnx voice model")
    if not os.path.isfile(voice):
        sys.exit(f"error: PIPER_VOICE model not found: {voice}")
    return piper, voice


def preflight_local_voice(document):
    """Validate the selected local engine and voices without creating output."""
    dialogue = is_dialogue(document)
    engine = pick_engine(dialogue=dialogue)
    if dialogue and engine != "kokoro":
        sys.exit("error: dialogue rough cuts require Kokoro for two local voices")
    config = {"engine": engine}

    if engine == "kokoro":
        if dialogue:
            try:
                groups = build_dialogue_groups(document, "local_voice")
            except ScriptFormatError as error:
                sys.exit(f"error: {error}")
            for group in groups.values():
                validate_kokoro_voice(group["voice"])
            config["groups"] = groups
            selected_voices = [group["voice"] for group in groups.values()]
        else:
            config["voice"] = validate_kokoro_voice(
                os.environ.get("KOKORO_VOICE", "am_michael")
            )
            selected_voices = [config["voice"]]
        validate_kokoro_runtime(selected_voices)
    else:
        config["piper_bin"], config["piper_voice"] = resolve_piper()

    return config


def reexec_into_kokoro_venv():
    """kokoro-onnx lives in its own venv; re-exec there so plain `python3` works."""
    try:
        import kokoro_onnx  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("GHOSTREEL_TTS_REEXEC"):
        sys.exit(f"kokoro venv is broken: kokoro_onnx not importable from {KOKORO_PY}")
    os.environ["GHOSTREEL_TTS_REEXEC"] = "1"
    os.execv(KOKORO_PY, [KOKORO_PY, os.path.abspath(__file__)] + sys.argv[1:])


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", path], capture_output=True, text=True)
    return float(out.stdout.strip() or 0.0)


def load_kokoro_engine():
    reexec_into_kokoro_venv()
    import logging
    logging.getLogger("kokoro_onnx").setLevel(logging.WARNING)
    import soundfile as sf
    from kokoro_onnx import Kokoro
    return Kokoro(KOKORO_MODEL, KOKORO_VOICES), sf


def make_kokoro(voice=None, engine=None):
    k, sf = engine or load_kokoro_engine()
    voice = voice or os.environ.get("KOKORO_VOICE", "am_michael")
    try:
        language, _ = voice_details(voice)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    speed = float(os.environ.get("KOKORO_SPEED", "1.0"))

    def speak(text, wav):
        samples, sr = k.create(text, voice=voice, speed=speed, lang=language.espeak_code)
        sf.write(wav, samples, sr)
    return speak


def make_piper(piper=None, voice=None):
    piper = piper or os.environ.get("PIPER_BIN") or shutil.which("piper") or sys.exit(
        "error: no local voice available.\n"
        "  best:     install Kokoro (see the docstring at the top of this file)\n"
        "  fallback: pip install piper-tts and set PIPER_BIN + PIPER_VOICE")
    voice = voice or os.environ.get("PIPER_VOICE") or sys.exit(
        "error: set PIPER_VOICE=/path/to/voice.onnx")

    def speak(text, wav):
        subprocess.run([piper, "--model", voice, "--output_file", wav],
                       input=text, text=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return speak


def main():
    preflight_only = len(sys.argv) > 1 and sys.argv[1] == "--preflight"
    if preflight_only:
        if len(sys.argv) != 3:
            sys.exit("usage: tts_local.py --preflight <script.json>")
        script_path = sys.argv[2]
    else:
        if len(sys.argv) != 3:
            sys.exit("usage: tts_local.py <script.json> <run_dir>")
        script_path = sys.argv[1]

    with open(script_path) as script_file:
        document = json.load(script_file)
    dialogue = is_dialogue(document)
    config = preflight_local_voice(document)
    engine = config["engine"]
    if preflight_only:
        print(f"LOCAL_VOICE_ENGINE={engine}")
        return

    beats = document["beats"]
    run = sys.argv[2]
    os.makedirs(os.path.join(run, "audio"), exist_ok=True)

    if dialogue:
        if engine != "kokoro":
            sys.exit("error: dialogue rough cuts require Kokoro for two local voices")
        groups = config["groups"]
        tracks = {}
        source_paths = {}
        kokoro_engine = load_kokoro_engine()
        with tempfile.TemporaryDirectory() as tmp:
            for index, (speaker, group) in enumerate(groups.items()):
                wav = os.path.join(tmp, f"speaker-{index}.wav")
                make_kokoro(group["voice"], kokoro_engine)(group["text"], wav)
                shape_pauses(wav, group["text"], group["spans"])
                duration = dur(wav)
                tracks[speaker] = approximate_track(
                    group["text"], group["spans"], duration
                )
                source_paths[speaker] = wav
            words, timing, segments = interleave_dialogue(beats, groups, tracks)
            stitch_audio(
                source_paths, segments, os.path.join(run, "audio", "vo.mp3")
            )
    else:
        speak = (
            make_kokoro(config["voice"])
            if engine == "kokoro"
            else make_piper(config["piper_bin"], config["piper_voice"])
        )
        text, spans = build_transcript(beats)
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "vo.wav")
            speak(text, wav)
            shape_pauses(wav, text, spans)
            duration = dur(wav)

            # Single synthesized WAV -> vo.mp3 (mono 44.1k, same contract as paid TTS).
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                            "-ac", "1", "-ar", "44100",
                            os.path.join(run, "audio", "vo.mp3")], check=True)
        words, timing = approximate_timings(text, spans, duration)

    json.dump(words, open(os.path.join(run, "audio", "words.json"), "w"), indent=1)
    json.dump(timing, open(os.path.join(run, "audio", "timing.json"), "w"), indent=1)
    print(f"ROUGH VO ({engine}, $0) -> {run}/audio/vo.mp3  ({timing['duration']:.1f}s)",
          file=sys.stderr)
    print("VO_CHARS=0")
    print(f"VO_DURATION={timing['duration']:.3f}")


if __name__ == "__main__":
    main()
