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

Usage: python3 src/tts_local.py <script.json> <run_dir>
Writes the same files as tts.py (vo.mp3, words.json, timing.json) so the rest of the
pipeline is identical. Word timings are approximate (spread across the continuous
transcript) — fine for reviewing flow; the paid pass gets exact alignment.
"""
import json, os, re, shutil, subprocess, sys, tempfile

from voices import voice_details

KOKORO_DIR = os.environ.get("KOKORO_DIR", os.path.expanduser("~/.local/share/kokoro-tts"))
KOKORO_PY = os.path.join(KOKORO_DIR, "venv/bin/python")
KOKORO_MODEL = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
KOKORO_VOICES = os.path.join(KOKORO_DIR, "voices-v1.0.bin")


def build_transcript(beats):
    """Join every beat for one continuous read and retain its character span."""
    full, spans = "", []
    for i, beat in enumerate(beats):
        say = beat["say"].strip()
        if i:
            full += "\n"
        start = len(full)
        full += say
        spans.append((start, len(full)))
    return full, spans


def approximate_timings(text, spans, duration):
    """Map transcript character positions onto the continuous audio duration."""
    scale = duration / len(text) if text else 0.0
    timing = {
        "duration": round(duration, 3),
        "beats": [
            {
                "audio_start": round(start * scale, 3),
                "audio_end": round(end * scale, 3),
            }
            for start, end in spans
        ],
    }
    words = [
        {
            "w": match.group().strip(".,!?;:"),
            "start": round(match.start() * scale, 3),
            "end": round(match.end() * scale, 3),
        }
        for match in re.finditer(r"\S+", text)
    ]
    return words, timing


def pick_engine():
    eng = os.environ.get("SCRATCH_ENGINE", "kokoro")
    if eng == "kokoro" and not (os.path.exists(KOKORO_MODEL) and os.path.exists(KOKORO_PY)):
        print(f"kokoro model/venv missing under {KOKORO_DIR} — falling back to piper",
              file=sys.stderr)
        eng = "piper"
    return eng


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


def make_kokoro():
    reexec_into_kokoro_venv()
    import logging
    logging.getLogger("kokoro_onnx").setLevel(logging.WARNING)
    import soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    voice = os.environ.get("KOKORO_VOICE", "am_michael")
    try:
        language, _ = voice_details(voice)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    speed = float(os.environ.get("KOKORO_SPEED", "1.0"))

    def speak(text, wav):
        samples, sr = k.create(text, voice=voice, speed=speed, lang=language.espeak_code)
        sf.write(wav, samples, sr)
    return speak


def make_piper():
    piper = os.environ.get("PIPER_BIN") or shutil.which("piper") or sys.exit(
        "error: no local voice available.\n"
        "  best:     install Kokoro (see the docstring at the top of this file)\n"
        "  fallback: pip install piper-tts and set PIPER_BIN + PIPER_VOICE")
    voice = os.environ.get("PIPER_VOICE") or sys.exit(
        "error: set PIPER_VOICE=/path/to/voice.onnx")

    def speak(text, wav):
        subprocess.run([piper, "--model", voice, "--output_file", wav],
                       input=text, text=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return speak


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: tts_local.py <script.json> <run_dir>")
    engine = pick_engine()
    speak = make_kokoro() if engine == "kokoro" else make_piper()

    beats = json.load(open(sys.argv[1]))["beats"]
    run = sys.argv[2]
    os.makedirs(os.path.join(run, "audio"), exist_ok=True)

    text, spans = build_transcript(beats)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "vo.wav")
        speak(text, wav)
        d = dur(wav)

        # Single synthesized WAV -> vo.mp3 (mono 44.1k, same contract as the paid pass).
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                        "-ac", "1", "-ar", "44100",
                        os.path.join(run, "audio", "vo.mp3")], check=True)

    words, timing = approximate_timings(text, spans, d)

    json.dump(words, open(os.path.join(run, "audio", "words.json"), "w"), indent=1)
    json.dump(timing, open(os.path.join(run, "audio", "timing.json"), "w"), indent=1)
    print(f"ROUGH VO ({engine}, $0) -> {run}/audio/vo.mp3  ({timing['duration']:.1f}s)",
          file=sys.stderr)
    print("VO_CHARS=0")
    print(f"VO_DURATION={timing['duration']:.3f}")


if __name__ == "__main__":
    main()
