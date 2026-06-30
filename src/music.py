#!/usr/bin/env python3
"""music.py — generate an instrumental music bed with ElevenLabs Music.

Clean-room. ElevenLabs Music draws from the same credit pool as the voice, so it's
"free" once you hold a plan. (Google Lyria via the Gemini API is an alternative — also
pay-per-use; swap the call if you prefer it.)

Env:   ELEVENLABS_API_KEY
Usage: python3 src/music.py --seconds 28 --out out/x/music.mp3 [--prompt "..."]
"""
import json, os, sys, urllib.request, urllib.error

API = "https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128"
DEFAULT = "upbeat modern instrumental, bright, energetic"


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 20.0
    out = a[a.index("--out") + 1]
    prompt = a[a.index("--prompt") + 1] if "--prompt" in a else DEFAULT
    key = os.environ.get("ELEVENLABS_API_KEY") or sys.exit("error: ELEVENLABS_API_KEY not set")

    ms = max(3000, min(int(secs * 1000), 300000))
    body = json.dumps({
        "prompt": f"{prompt}. INSTRUMENTAL ONLY. NO VOCALS. NO RAP.",
        "music_length_ms": ms,
    }).encode()
    req = urllib.request.Request(API, data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"music failed ({e.code}): {e.read().decode(errors='replace')[:300]}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(audio)
    print(f"music -> {out} ({ms/1000:.0f}s)")


if __name__ == "__main__":
    main()
