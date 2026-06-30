#!/usr/bin/env python3
"""tts_piper.py — FREE local voiceover for rough cuts (Piper). $0, no API.

Build the WHOLE video with this robot voice first. Watch it end to end: does the script
breathe, do the screen-to-screen cuts land? Re-edit for nothing. Only when it's right do
you pay for the real voice (src/tts.py). This is the single biggest cost-saver.

Get Piper:  pip install piper-tts   (then download a voice .onnx + .onnx.json from
            https://github.com/rhasspy/piper/releases or huggingface rhasspy/piper-voices)
Point at it: export PIPER_BIN=piper   PIPER_VOICE=/path/to/en_US-amy-medium.onnx

Usage: python3 src/tts_piper.py <script.json> <run_dir>
Writes the same files as tts.py (vo.mp3, words.json, timing.json) so the rest of the
pipeline is identical. Word timings are approximate (evenly spread per beat) — fine for
reviewing flow; the paid pass gets exact alignment.
"""
import json, os, shutil, subprocess, sys, tempfile

def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", path], capture_output=True, text=True)
    return float(out.stdout.strip() or 0.0)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: tts_piper.py <script.json> <run_dir>")
    beats = json.load(open(sys.argv[1]))["beats"]
    run = sys.argv[2]
    piper = os.environ.get("PIPER_BIN") or shutil.which("piper") or sys.exit(
        "error: Piper not found. pip install piper-tts and set PIPER_BIN / PIPER_VOICE.")
    voice = os.environ.get("PIPER_VOICE") or sys.exit("error: set PIPER_VOICE=/path/to/voice.onnx")

    os.makedirs(os.path.join(run, "audio"), exist_ok=True)
    tmp = tempfile.mkdtemp()
    wavs, timing = [], {"duration": 0.0, "beats": []}
    words, t = [], 0.0
    for i, b in enumerate(beats):
        wav = os.path.join(tmp, f"{i}.wav")
        subprocess.run([piper, "--model", voice, "--output_file", wav],
                       input=b["say"].strip(), text=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        d = dur(wav)
        wavs.append(wav)
        timing["beats"].append({"audio_start": round(t, 3), "audio_end": round(t + d, 3)})
        toks = b["say"].split()
        for j, w in enumerate(toks):  # spread words evenly across the beat
            ws = t + d * j / max(1, len(toks))
            we = t + d * (j + 1) / max(1, len(toks))
            words.append({"w": w.strip(".,!?;:"), "start": round(ws, 3), "end": round(we, 3)})
        t += d
    timing["duration"] = round(t, 3)

    # concat wavs -> vo.mp3
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("\n".join(f"file '{w}'" for w in wavs))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", lst, "-ac", "1", "-ar", "44100", os.path.join(run, "audio", "vo.mp3")], check=True)

    json.dump(words, open(os.path.join(run, "audio", "words.json"), "w"), indent=1)
    json.dump(timing, open(os.path.join(run, "audio", "timing.json"), "w"), indent=1)
    print(f"ROUGH VO (Piper, $0) -> {run}/audio/vo.mp3  ({timing['duration']:.1f}s)", file=sys.stderr)
    print(f"VO_CHARS=0")
    print(f"VO_DURATION={timing['duration']:.3f}")


if __name__ == "__main__":
    main()
