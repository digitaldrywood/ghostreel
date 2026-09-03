#!/usr/bin/env bash
# music.sh — generate or reuse an instrumental bed, then mix it into final.mp4.
#
#   bash src/music.sh scenes.json out/
#
# Expects out/final.mp4 from assemble.sh. When out/music.mp3 already exists, the stage
# reuses it; otherwise music.py generates a bed for the assembled video's duration.
set -euo pipefail

SCENES="${1:?usage: music.sh scenes.json out/}"
OUT="${2:?usage: music.sh scenes.json out/}"
FINAL="$OUT/final.mp4"
BED="$OUT/music.mp3"

if [ ! -f "$FINAL" ]; then
  echo "missing assembled video: $FINAL (run src/assemble.sh first)" >&2
  exit 1
fi

if [ ! -f "$BED" ]; then
  DURATION="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FINAL")"
  PROMPT="$(python3 - "$SCENES" <<'PY'
import json
import sys

scenes = json.load(open(sys.argv[1]))
print(scenes.get("music_prompt", "upbeat modern instrumental, bright, energetic"))
PY
)"
  python3 "$(dirname "$0")/music.py" --seconds "$DURATION" --out "$BED" --prompt "$PROMPT"
else
  echo "reusing $BED"
fi

MIXED="$(mktemp "$OUT/.final-with-music.XXXXXX.mp4")"
trap 'rm -f "$MIXED"' EXIT

# Keep the voice at full level, loop the bed beneath its complete duration, and normalize
# both inputs to mono before mixing so a stereo bed cannot garble the voice track.
ffmpeg -nostdin -y -loglevel error -i "$FINAL" -stream_loop -1 -i "$BED" \
  -filter_complex "[0:a:0]aformat=channel_layouts=mono[v];[1:a:0]aformat=channel_layouts=mono,volume=0.10[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]" \
  -map 0:v:0 -map "[a]" -map_metadata 0 -c:v copy -c:a aac -ac 1 \
  -movflags +faststart "$MIXED"

mv "$MIXED" "$FINAL"
trap - EXIT
echo "mixed $BED into $FINAL"
