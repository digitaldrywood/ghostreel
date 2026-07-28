#!/usr/bin/env bash
# assemble.sh — cut visuals to the voice and produce the final mp4.
#
#   bash src/assemble.sh scenes.json out/
#
# Expects (produced by earlier stages):
#   out/vo.mp3            the continuous voiceover            (src/tts.py)
#   out/words.json        word-level timings                 (src/tts.py)
#   out/render/NN.png     one rendered visual per beat, 0-indexed  (your render step)
#   out/music.mp3         optional instrumental bed
#
# Writes out/final.mp4. ffmpeg does all the work; the only clever part is computing each
# visual's on-screen window from the word timings so the cut lands on the right word.
set -euo pipefail

SCENES="${1:?usage: assemble.sh scenes.json out/}"
OUT="${2:?usage: assemble.sh scenes.json out/}"
W=1920; H=1080
case "$(python3 -c "import json;print(json.load(open('$SCENES')).get('aspect','16:9'))")" in
  9:16) W=1080; H=1920 ;;
esac
BG=0x0a0a0f
mkdir -p "$OUT/seg"

# --- compute each beat's [start,duration] window from the word timings -------------
# Walk words.json in order, assigning N words to each beat (N = words in that beat's say).
# A beat starts at its cue word if given, else its first word. It holds until the next
# beat starts. Output: "index start duration" lines.
python3 - "$SCENES" "$OUT/words.json" > "$OUT/windows.txt" <<'PY'
import json, sys
scenes = json.load(open(sys.argv[1]))["beats"]
words = json.load(open(sys.argv[2]))
total = words[-1]["end"] if words else 0.0
starts, i = [], 0
for b in scenes:
    n = len(b["say"].split())
    span = words[i:i+n] or [{"start": total, "end": total}]
    start = span[0]["start"]
    cue = b.get("cue")
    if cue:                       # cut in on the concept word, if present in this span
        cw = cue.split()[0].strip(".,!?").lower()
        for w in span:
            if w["w"].strip(".,!?").lower() == cw:
                start = w["start"]; break
    starts.append(start)
    i += n
for idx in range(len(scenes)):
    s = starts[idx]
    e = starts[idx + 1] if idx + 1 < len(starts) else total
    print(idx, f"{s:.3f}", f"{max(0.3, e - s):.3f}")  # min 0.3s guard
PY

# --- build one frame-snapped segment per beat -------------------------------------
SEGS=()
while read -r idx start dur; do
  vis="$OUT/render/$(printf '%02d' "$idx").png"
  [ -f "$vis" ] || { echo "missing visual: $vis (run your render step)"; exit 1; }
  seg="$OUT/seg/$(printf '%02d' "$idx").mp4"
  ffmpeg -y -loglevel error -loop 1 -t "$dur" -i "$vis" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:${BG},setsar=1,fps=30" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p "$seg"
  SEGS+=("$seg")
done < "$OUT/windows.txt"

# --- concat the visuals, then mux the (mono) voice and optional music -------------
: > "$OUT/concat.txt"
for s in "${SEGS[@]}"; do echo "file '$(realpath "$s")'" >> "$OUT/concat.txt"; done
ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/concat.txt" -c copy "$OUT/visual.mp4"

if [ -f "$OUT/music.mp3" ]; then
  # voice at full, music ducked under it; everything forced to mono so nothing garbles
  ffmpeg -y -loglevel error -i "$OUT/visual.mp4" -i "$OUT/vo.mp3" -stream_loop -1 -i "$OUT/music.mp3" \
    -filter_complex "[1:a]aformat=channel_layouts=mono[v];[2:a]aformat=channel_layouts=mono,volume=0.10[m];[v][m]amix=inputs=2:duration=first[a]" \
    -map 0:v -map "[a]" -c:v copy -c:a aac -ac 1 -shortest -movflags +faststart "$OUT/final.mp4"
else
  ffmpeg -y -loglevel error -i "$OUT/visual.mp4" -i "$OUT/vo.mp3" \
    -map 0:v -map 1:a -c:v copy -c:a aac -ac 1 -shortest -movflags +faststart "$OUT/final.mp4"
fi

echo "wrote $OUT/final.mp4"
