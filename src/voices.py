#!/usr/bin/env python3
"""Discover, audition, and publish the Kokoro voices bundled with ghostreel."""

from __future__ import annotations

import argparse
import html
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KOKORO_DIR = Path.home() / ".local/share/kokoro-tts"
DEFAULT_GALLERY_DIR = REPO_ROOT / "docs/voices"


@dataclass(frozen=True)
class VoiceLanguage:
    """Language metadata shared by synthesis, the CLI, and the gallery."""

    name: str
    html_lang: str
    espeak_code: str
    sample: str
    female: tuple[str, ...]
    male: tuple[str, ...]


LANGUAGES = (
    VoiceLanguage(
        "American English",
        "en-US",
        "en-us",
        "This is a sample of the Kokoro voice. Choose the voice that fits your story.",
        (
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
            "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        ),
        (
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
            "am_michael", "am_onyx", "am_puck", "am_santa",
        ),
    ),
    VoiceLanguage(
        "British English",
        "en-GB",
        "en-gb",
        "This is a sample of the Kokoro voice. Choose the voice that suits your story.",
        ("bf_alice", "bf_emma", "bf_isabella", "bf_lily"),
        ("bm_daniel", "bm_fable", "bm_george", "bm_lewis"),
    ),
    VoiceLanguage(
        "Spanish",
        "es",
        "es",
        "Esta es una muestra de la voz Kokoro. Elige la voz que mejor se adapte a tu historia.",
        ("ef_dora",),
        ("em_alex", "em_santa"),
    ),
    VoiceLanguage(
        "French",
        "fr",
        "fr-fr",
        "Voici un exemple de la voix Kokoro. Choisissez la voix qui correspond à votre histoire.",
        ("ff_siwis",),
        (),
    ),
    VoiceLanguage(
        "Hindi",
        "hi",
        "hi",
        "यह कोकोरो आवाज़ का एक नमूना है। अपनी कहानी के लिए सही आवाज़ चुनें।",
        ("hf_alpha", "hf_beta"),
        ("hm_omega", "hm_psi"),
    ),
    VoiceLanguage(
        "Italian",
        "it",
        "it",
        "Questo è un esempio della voce Kokoro. Scegli la voce più adatta alla tua storia.",
        ("if_sara",),
        ("im_nicola",),
    ),
    VoiceLanguage(
        "Japanese",
        "ja",
        "ja",
        "これは音声サンプルです。",
        ("jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro"),
        ("jm_kumo",),
    ),
    VoiceLanguage(
        "Brazilian Portuguese",
        "pt-BR",
        "pt-br",
        "Esta é uma amostra da voz Kokoro. Escolha a voz que combina com a sua história.",
        ("pf_dora",),
        ("pm_alex", "pm_santa"),
    ),
    VoiceLanguage(
        "Mandarin Chinese",
        "zh-CN",
        "cmn",
        "这是一个语音示例。请选择适合您故事的声音。",
        ("zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi"),
        ("zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"),
    ),
)

VOICE_INDEX = {
    voice: (language, gender)
    for language in LANGUAGES
    for gender, voices in (("female", language.female), ("male", language.male))
    for voice in voices
}


def voice_details(voice: str) -> tuple[VoiceLanguage, str]:
    """Return language and gender metadata or fail with a useful CLI hint."""
    try:
        return VOICE_INDEX[voice]
    except KeyError as exc:
        raise ValueError(
            f"unknown Kokoro voice: {voice!r}; run ./ghostreel.sh --voices to list choices"
        ) from exc


def print_voice_table() -> None:
    """Print a copyable Markdown table containing all bundled voice ids."""
    print("| Language | Female voices | Male voices |")
    print("| --- | --- | --- |")
    for language in LANGUAGES:
        female = ", ".join(language.female) or "—"
        male = ", ".join(language.male) or "—"
        print(f"| {language.name} | {female} | {male} |")
    print(f"\n{len(VOICE_INDEX)} voices. Audition one with ./ghostreel.sh --sample <voice>.")


def _kokoro_paths() -> tuple[Path, Path, Path]:
    root = Path(os.environ.get("KOKORO_DIR", DEFAULT_KOKORO_DIR)).expanduser()
    return root / "venv/bin/python", root / "kokoro-v1.0.onnx", root / "voices-v1.0.bin"


def _reexec_into_kokoro_venv(kokoro_python: Path) -> None:
    try:
        import kokoro_onnx  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("GHOSTREEL_VOICES_REEXEC"):
        raise SystemExit(f"kokoro venv is broken: kokoro_onnx not importable from {kokoro_python}")
    os.environ["GHOSTREEL_VOICES_REEXEC"] = "1"
    os.execv(
        str(kokoro_python),
        [str(kokoro_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )


def _load_kokoro():
    kokoro_python, model_path, voices_path = _kokoro_paths()
    missing = [path for path in (kokoro_python, model_path, voices_path) if not path.exists()]
    if missing:
        joined = "\n  ".join(str(path) for path in missing)
        raise SystemExit(f"Kokoro is not installed; missing:\n  {joined}\nSee README.md for setup.")
    _reexec_into_kokoro_venv(kokoro_python)

    import logging
    logging.getLogger("kokoro_onnx").setLevel(logging.WARNING)
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(model_path), str(voices_path))
    missing_voices = sorted(set(VOICE_INDEX) - set(kokoro.voices))
    if missing_voices:
        raise SystemExit(f"voices-v1.0.bin is missing catalog voices: {', '.join(missing_voices)}")
    return kokoro


def _write_wav(kokoro, voice: str, path: Path) -> None:
    import soundfile as sf

    language, _ = voice_details(voice)
    speed = float(os.environ.get("KOKORO_SPEED", "1.0"))
    samples, sample_rate = kokoro.create(
        language.sample,
        voice=voice,
        speed=speed,
        lang=language.espeak_code,
    )
    sf.write(path, samples, sample_rate)


def _player_command(path: Path) -> list[str]:
    configured = os.environ.get("GHOSTREEL_SAMPLE_PLAYER")
    if configured:
        command = shlex.split(configured)
        if not command:
            raise SystemExit("GHOSTREEL_SAMPLE_PLAYER is empty")
        return [*command, str(path)]

    candidates = (
        ("afplay", ()),
        ("paplay", ()),
        ("play", ("-q",)),
        ("aplay", ("-q",)),
        ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "error")),
    )
    for executable, arguments in candidates:
        if shutil.which(executable):
            return [executable, *arguments, str(path)]
    raise SystemExit(
        "no audio player found; install afplay, PulseAudio, SoX, ALSA, or ffplay, "
        "or set GHOSTREEL_SAMPLE_PLAYER"
    )


def play_sample(voice: str) -> None:
    language, gender = voice_details(voice)
    kokoro = _load_kokoro()
    with tempfile.TemporaryDirectory(prefix="ghostreel-voice-") as temp_dir:
        wav_path = Path(temp_dir) / f"{voice}.wav"
        _write_wav(kokoro, voice, wav_path)
        print(f"Playing {voice} — {language.name}, {gender}", file=sys.stderr)
        try:
            subprocess.run(_player_command(wav_path), check=True)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                f"audio player exited with status {exc.returncode}; "
                "set GHOSTREEL_SAMPLE_PLAYER to another player"
            ) from exc


def render_gallery(output_dir: Path = DEFAULT_GALLERY_DIR) -> Path:
    """Write the deterministic gallery page and return its path."""
    cards = []
    for language in LANGUAGES:
        voices = []
        for gender, voice_ids in (("Female", language.female), ("Male", language.male)):
            for voice in voice_ids:
                escaped = html.escape(voice)
                voices.append(
                    f'''<article class="voice-card">
          <div><code>{escaped}</code><span>{gender}</span></div>
          <audio controls preload="none" src="{escaped}.mp3">
            <a href="{escaped}.mp3">Download {escaped} sample</a>
          </audio>
          <a class="download" href="{escaped}.mp3">Raw MP3</a>
        </article>'''
                )
        cards.append(
            f'''<section lang="{language.html_lang}">
      <h2>{html.escape(language.name)}</h2>
      <p class="sample">{html.escape(language.sample)}</p>
      <div class="voice-grid">{"".join(voices)}</div>
    </section>'''
        )

    document = f'''<!doctype html>
<!-- Generated by: python3 src/voices.py gallery -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Playable samples of all 54 local Kokoro voices in ghostreel.">
  <title>ghostreel Kokoro voice gallery</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0b0a12; color: #f7f3ff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at top, #292044 0, #0b0a12 42rem); }}
    main {{ width: min(72rem, calc(100% - 2rem)); margin: 0 auto; padding: 5rem 0; }}
    header {{ max-width: 48rem; margin-bottom: 3.5rem; }}
    .eyebrow {{ color: #e9b8ff; font-size: .78rem; font-weight: 800; letter-spacing: .18em; text-transform: uppercase; }}
    h1 {{ margin: .4rem 0 1rem; font-size: clamp(2.5rem, 7vw, 5.5rem); line-height: .95; letter-spacing: -.05em; }}
    header p, .sample {{ color: #c9c2d8; line-height: 1.65; }}
    section {{ margin-top: 3.5rem; scroll-margin-top: 1rem; }}
    h2 {{ margin-bottom: .25rem; font-size: 1.6rem; }}
    .sample {{ margin-top: 0; font-size: .92rem; }}
    .voice-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); gap: .85rem; }}
    .voice-card {{ padding: 1rem; border: 1px solid #43385d; border-radius: 1rem; background: rgba(24, 20, 36, .86); box-shadow: 0 1rem 2.8rem rgba(0, 0, 0, .16); }}
    .voice-card div {{ display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-bottom: .8rem; }}
    code {{ color: #fff; font: 700 .95rem ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .voice-card span {{ color: #a99fba; font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
    audio {{ width: 100%; height: 2.6rem; }}
    a {{ color: #e9b8ff; }}
    .download {{ display: inline-block; margin-top: .65rem; font-size: .8rem; }}
    footer {{ margin-top: 4rem; color: #8f879c; font-size: .85rem; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">ghostreel · local voice discovery</div>
      <h1>Pick the voice before you cut.</h1>
      <p>Every sample below runs locally with Kokoro. Each voice reads a line written for its own language, and every file is a mono 64 kbps MP3.</p>
    </header>
    {"".join(cards)}
    <footer>Regenerate all samples and this page with <code>python3 src/voices.py gallery</code>.</footer>
  </main>
</body>
</html>
'''
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.html"
    index_path.write_text(document, encoding="utf-8")
    return index_path


def generate_gallery(output_dir: Path = DEFAULT_GALLERY_DIR) -> None:
    ffmpeg = shutil.which("ffmpeg") or raise_missing_ffmpeg()
    kokoro = _load_kokoro()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ghostreel-gallery-") as temp_dir:
        stage_dir = Path(temp_dir)
        for index, voice in enumerate(VOICE_INDEX, start=1):
            wav_path = stage_dir / f"{voice}.wav"
            mp3_path = stage_dir / f"{voice}.mp3"
            _write_wav(kokoro, voice, wav_path)
            subprocess.run(
                [
                    ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path),
                    "-map_metadata", "-1", "-ac", "1", "-ar", "24000",
                    "-codec:a", "libmp3lame", "-b:a", "64k", str(mp3_path),
                ],
                check=True,
            )
            shutil.copyfile(mp3_path, output_dir / mp3_path.name)
            print(f"[{index:02d}/{len(VOICE_INDEX)}] {voice}", file=sys.stderr)

    index_path = render_gallery(output_dir)
    print(f"Voice gallery -> {index_path} ({len(VOICE_INDEX)} samples)")


def raise_missing_ffmpeg():
    raise SystemExit("ffmpeg is required to encode gallery samples as 64 kbps MP3")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="print all bundled voice ids")
    sample = subparsers.add_parser("sample", help="generate and play one local sample")
    sample.add_argument("voice", help="voice id from the list command")
    gallery = subparsers.add_parser("gallery", help="regenerate all MP3 samples and index.html")
    gallery.add_argument("--output", type=Path, default=DEFAULT_GALLERY_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "list":
        print_voice_table()
    elif args.command == "sample":
        try:
            play_sample(args.voice)
        except ValueError as exc:
            raise SystemExit(f"error: {exc}") from exc
    else:
        generate_gallery(args.output)


if __name__ == "__main__":
    main()
