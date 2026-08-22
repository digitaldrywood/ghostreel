#!/usr/bin/env bash
# assemble.sh — cut visuals to the voice and produce the final mp4.
#
#   bash src/assemble.sh scenes.json out/
#
# Expects (produced by earlier stages):
#   out/audio/vo.mp3      the continuous voiceover            (src/tts.py)
#   out/audio/words.json  word-level timings                  (src/tts.py)
#   out/render/NN.png     a still rendered visual, 0-indexed       (your render step)
#   out/render/NN.mp4     or a moving render; provide one or the other per beat
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
# A beat starts at its complete cue phrase if given, else its first word. It holds until
# the next beat starts, provided that leaves five seconds for a diagram or four seconds
# for any other still. Output: "index start duration" lines.
python3 - "$SCENES" "$OUT/audio/words.json" > "$OUT/windows.txt" <<'PY'
import json
import sys
import unicodedata


def normalize_word(value):
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character)[0] in {"L", "N"}
    )


def cue_position(beat_index, cue, span):
    cue_words = [normalize_word(word) for word in cue.split()]
    cue_words = [word for word in cue_words if word]
    if not cue_words:
        raise SystemExit(f"beat {beat_index}: cue {cue!r} has no matchable words")

    normalized_span = [
        (index, normalized)
        for index, word in enumerate(span)
        if (normalized := normalize_word(word["w"]))
    ]
    span_words = [normalized for _, normalized in normalized_span]
    width = len(cue_words)
    matches = [
        index
        for index in range(len(span_words) - width + 1)
        if span_words[index:index + width] == cue_words
    ]
    if not matches:
        raise SystemExit(
            f"beat {beat_index}: cue {cue!r} was not found in its aligned word span"
        )
    if len(matches) > 1:
        offsets = ", ".join(str(normalized_span[index][0]) for index in matches)
        raise SystemExit(
            f"beat {beat_index}: cue {cue!r} is ambiguous in its aligned word span "
            f"(matches at word offsets {offsets})"
        )
    word_offset = normalized_span[matches[0]][0]
    return word_offset, span[word_offset]["start"]


scenes = json.load(open(sys.argv[1]))["beats"]
words = json.load(open(sys.argv[2]))
total = words[-1]["end"] if words else 0.0
starts, i = [], 0
for beat_index, b in enumerate(scenes):
    n = len(b["say"].split())
    span = words[i:i+n] or [{"w": "", "start": total, "end": total}]
    start = span[0]["start"]
    cue = b.get("cue")
    if cue:
        cue_offset, start = cue_position(beat_index, cue, span)
        if beat_index == 0:
            if cue_offset:
                raise SystemExit(
                    f"beat 0: cue {cue!r} starts at word offset {cue_offset} and "
                    "leaves the opening audio without a visual; move or remove the cue "
                    "so the first visual starts at zero"
                )
            start = 0.0
    elif beat_index == 0:
        start = 0.0
    starts.append(start)
    i += n
for idx in range(len(scenes)):
    s = starts[idx]
    e = starts[idx + 1] if idx + 1 < len(starts) else total
    duration = e - s
    visual_type = scenes[idx].get("show", {}).get("type", "still")
    minimum = 5.0 if visual_type == "diagram" else 4.0
    if duration + 1e-9 < minimum:
        if idx + 1 < len(scenes):
            boundary = f"beat {idx + 1} starts"
            remedy = f"move beat {idx + 1}'s cue later or revise the storyboard"
        elif scenes[idx].get("cue"):
            boundary = "audio ends"
            remedy = "move this beat's cue earlier, lengthen narration, or revise the storyboard"
        else:
            boundary = "audio ends"
            remedy = "lengthen narration or revise the storyboard"
        raise SystemExit(
            f"beat {idx} ({visual_type}): requires at least {minimum:.3f}s dwell, "
            f"but cue timing leaves {max(0.0, duration):.3f}s before {boundary}; "
            f"{remedy}"
        )
    print(idx, f"{s:.3f}", f"{duration:.3f}")
PY

# --- build one frame-snapped segment per beat -------------------------------------
SEGS=()
while read -r idx start dur; do
  stem="$OUT/render/$(printf '%02d' "$idx")"
  still="$stem.png"
  video="$stem.mp4"
  if [ -f "$still" ] && [ -f "$video" ]; then
    echo "ambiguous visual for beat $idx: found both $still and $video; keep exactly one" >&2
    exit 1
  elif [ -f "$video" ]; then
    vis="$video"
    input_args=(-stream_loop -1 -i "$vis")
  elif [ -f "$still" ]; then
    vis="$still"
    input_args=(-loop 1 -i "$vis")
  else
    echo "missing visual for beat $idx: expected $still or $video (run your render step)" >&2
    exit 1
  fi
  seg="$OUT/seg/$(printf '%02d' "$idx").mp4"
  ffmpeg -nostdin -y -loglevel error "${input_args[@]}" -map 0:v:0 -t "$dur" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:${BG},setsar=1,fps=30" \
    -an -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p "$seg"
  SEGS+=("$seg")
done < "$OUT/windows.txt"

# --- concat the visuals, then mux the (mono) voice and optional music -------------
: > "$OUT/concat.txt"
for s in "${SEGS[@]}"; do echo "file '$(realpath "$s")'" >> "$OUT/concat.txt"; done
ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/concat.txt" -c copy "$OUT/visual.mp4"

if [ -f "$OUT/music.mp3" ]; then
  # voice at full, music ducked under it; everything forced to mono so nothing garbles
  ffmpeg -y -loglevel error -i "$OUT/visual.mp4" -i "$OUT/audio/vo.mp3" -stream_loop -1 -i "$OUT/music.mp3" \
    -filter_complex "[1:a]aformat=channel_layouts=mono[v];[2:a]aformat=channel_layouts=mono,volume=0.10[m];[v][m]amix=inputs=2:duration=first[a]" \
    -map 0:v -map "[a]" -c:v copy -c:a aac -ac 1 -shortest -movflags +faststart "$OUT/final.mp4"
else
  ffmpeg -y -loglevel error -i "$OUT/visual.mp4" -i "$OUT/audio/vo.mp3" \
    -map 0:v -map 1:a -c:v copy -c:a aac -ac 1 -shortest -movflags +faststart "$OUT/final.mp4"
fi

echo "wrote $OUT/final.mp4"
