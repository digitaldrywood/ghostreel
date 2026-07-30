#!/usr/bin/env python3
"""tts.py — turn a script into a continuous voiceover with word-level timings.

Narrator scripts use one TTS call. Dialogue scripts use one call per speaker, then slice
and interleave those two continuous performances in turn order. Neither path synthesizes
individual beats. Character alignment keeps every visual and caption on the global track.

Works for both flavors: an explainer `scenes.json` and a reel `intake.json` — both are
just `{"beats":[{"say": "...", ...}]}` with an optional top-level `voice_id`.

Env:   ELEVENLABS_API_KEY   (and voice via intake.voice_id or ELEVENLABS_VOICE_ID)
Usage: python3 src/tts.py <script.json> <run_dir>
Writes: <run>/audio/vo.mp3, <run>/audio/words.json, <run>/audio/timing.json
Prints: VO_CHARS=<n>  VO_DURATION=<secs>

Free rough cuts: use src/tts_local.py instead (Kokoro, local, $0) before you pay for this.
This file is intentionally small and unframeworked — read it, adapt it.
"""
import base64, json, os, sys, tempfile, urllib.request, urllib.error

from tts_common import (
    ScriptFormatError,
    alignment_track,
    build_dialogue_groups,
    build_transcript,
    interleave_dialogue,
    is_dialogue,
    narrator_outputs,
    stitch_audio,
)

MODEL = "eleven_multilingual_v2"


def synth(text, voice, key):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128"
    body = json.dumps({
        "text": text, "model_id": MODEL,
        "voice_settings": {"stability": 0.42, "similarity_boost": 0.82,
                           "style": 0.30, "use_speaker_boost": True},
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs TTS failed ({e.code}): {e.read().decode(errors='replace')[:400]}")


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: tts.py <script.json> <run_dir>")
    doc = json.load(open(sys.argv[1]))
    run = sys.argv[2]
    beats = doc["beats"]
    key = os.environ.get("ELEVENLABS_API_KEY") or sys.exit("error: ELEVENLABS_API_KEY not set (cp .envrc.example .envrc; direnv allow)")
    os.makedirs(os.path.join(run, "audio"), exist_ok=True)
    output_path = os.path.join(run, "audio", "vo.mp3")

    if is_dialogue(doc):
        try:
            groups = build_dialogue_groups(doc, "voice_id")
        except ScriptFormatError as error:
            sys.exit(f"error: {error}")
        tracks = {}
        source_paths = {}
        with tempfile.TemporaryDirectory() as tmp:
            for index, (speaker, group) in enumerate(groups.items()):
                data = synth(group["text"], group["voice"], key)
                source = os.path.join(tmp, f"speaker-{index}.mp3")
                with open(source, "wb") as handle:
                    handle.write(base64.b64decode(data["audio_base64"]))
                alignment = data.get("alignment") or data.get("normalized_alignment")
                if not alignment:
                    sys.exit(f'error: TTS returned no alignment for speaker "{speaker}"')
                try:
                    tracks[speaker] = alignment_track(
                        group["text"], group["spans"], alignment
                    )
                except ScriptFormatError as error:
                    sys.exit(f"error: {error}")
                source_paths[speaker] = source
            words, timing, segments = interleave_dialogue(beats, groups, tracks)
            stitch_audio(source_paths, segments, output_path)
        character_count = sum(len(group["text"]) for group in groups.values())
    else:
        voice = doc.get("voice_id") or os.environ.get("ELEVENLABS_VOICE_ID") or sys.exit("error: set voice_id in the script or ELEVENLABS_VOICE_ID")
        text, spans = build_transcript(beats)
        data = synth(text, voice, key)
        with open(output_path, "wb") as handle:
            handle.write(base64.b64decode(data["audio_base64"]))
        alignment = data.get("alignment") or data.get("normalized_alignment")
        if not alignment:
            sys.exit("error: TTS returned no alignment")
        try:
            words, timing = narrator_outputs(alignment_track(text, spans, alignment))
        except ScriptFormatError as error:
            sys.exit(f"error: {error}")
        character_count = len(text)

    json.dump(words, open(os.path.join(run, "audio", "words.json"), "w"), indent=1)
    json.dump(timing, open(os.path.join(run, "audio", "timing.json"), "w"), indent=1)
    print(f"VO -> {run}/audio/vo.mp3  ({character_count} chars, {timing['duration']:.1f}s, {len(words)} words)", file=sys.stderr)
    print(f"VO_CHARS={character_count}")
    print(f"VO_DURATION={timing['duration']:.3f}")


if __name__ == "__main__":
    main()
