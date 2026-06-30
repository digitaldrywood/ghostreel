#!/usr/bin/env python3
"""tts.py — turn a script (list of `beats`, each with a `say`) into ONE continuous
voiceover with word-level timings.

The whole point: send the entire script to the TTS in a SINGLE call, not beat by beat.
Per-beat clips sound disjointed. We keep the character/word alignment so the assembler
can cut each visual to the exact word it belongs to.

Works for both flavors: an explainer `scenes.json` and a reel `intake.json` — both are
just `{"beats":[{"say": "...", ...}]}` with an optional top-level `voice_id`.

Env:   ELEVENLABS_API_KEY   (and voice via intake.voice_id or ELEVENLABS_VOICE_ID)
Usage: python3 src/tts.py <script.json> <run_dir>
Writes: <run>/audio/vo.mp3, <run>/audio/words.json, <run>/audio/timing.json
Prints: VO_CHARS=<n>  VO_DURATION=<secs>

Free rough cuts: use src/tts_piper.py instead (local, $0) before you pay for this.
This file is intentionally small and unframeworked — read it, adapt it.
"""
import base64, json, os, sys, urllib.request, urllib.error

MODEL = "eleven_multilingual_v2"


def build_transcript(beats):
    """One continuous read. Blank line between beats — whitespace paces it. Never insert
    <break> tags; they make the read halting. Returns (text, [(char_start,char_end)...])."""
    full, spans = "", []
    for i, b in enumerate(beats):
        say = b["say"].strip()
        if i:
            full += "\n"
        s = len(full)
        full += say
        spans.append((s, len(full)))
    return full, spans


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
    voice = doc.get("voice_id") or os.environ.get("ELEVENLABS_VOICE_ID") or sys.exit("error: set voice_id in the script or ELEVENLABS_VOICE_ID")

    text, spans = build_transcript(beats)
    data = synth(text, voice, key)

    os.makedirs(os.path.join(run, "audio"), exist_ok=True)
    open(os.path.join(run, "audio", "vo.mp3"), "wb").write(base64.b64decode(data["audio_base64"]))

    al = data.get("alignment") or data.get("normalized_alignment")
    chars, cs, ce = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    duration = ce[-1] if ce else 0.0

    # per-beat windows from the char spans
    timing = {"duration": round(duration, 3), "beats": []}
    for (s, e) in spans:
        e = min(e, len(chars))
        timing["beats"].append({
            "audio_start": round(cs[s] if s < len(cs) else 0.0, 3),
            "audio_end": round(ce[e - 1] if 0 < e <= len(ce) else duration, 3),
        })

    # words for the SRT
    words, cur, w0, w1 = [], "", None, None
    for ch, a, b in zip(chars, cs, ce):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "start": round(w0, 3), "end": round(w1, 3)})
                cur, w0, w1 = "", None, None
        else:
            if not cur:
                w0 = a
            cur += ch
            w1 = b
    if cur:
        words.append({"w": cur, "start": round(w0, 3), "end": round(w1, 3)})

    json.dump(words, open(os.path.join(run, "audio", "words.json"), "w"), indent=1)
    json.dump(timing, open(os.path.join(run, "audio", "timing.json"), "w"), indent=1)
    print(f"VO -> {run}/audio/vo.mp3  ({len(text)} chars, {duration:.1f}s, {len(words)} words)", file=sys.stderr)
    print(f"VO_CHARS={len(text)}")
    print(f"VO_DURATION={duration:.3f}")


if __name__ == "__main__":
    main()
