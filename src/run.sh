#!/usr/bin/env bash
# run.sh — the end-to-end pipeline, in order. This is the map; each step is a real script
# you can run on its own. Read it top to bottom to understand the whole method.
#
#   bash src/run.sh examples/narration.example.md examples/scenes.example.json
#
# The first form is prose-first. Existing scenes.json visual assignments are
# preserved while its narration is regenerated. Passing scenes.json alone is
# retained for existing projects that have not moved their prose upstream yet.
#
# Stages that cost money are marked. Build a free rough cut first, approve, then pay.
set -euo pipefail
SOURCE="${1:-examples/narration.example.md}"
PROSE=""
case "$SOURCE" in
  *.md)
    PROSE="$SOURCE"
    DEFAULT_OUT="out/$(basename "${PROSE%.md}")"
    SCENES="${2:-$DEFAULT_OUT/scenes.json}"
    OUT="${GHOSTREEL_OUT:-$DEFAULT_OUT}"
    ;;
  *.json)
    SCENES="$SOURCE"
    OUT="${GHOSTREEL_OUT:-out/$(basename "${SCENES%.json}")}"
    ;;
  *)
    echo "usage: bash src/run.sh <narration.md> [scenes.json]" >&2
    echo "   or: bash src/run.sh <scenes.json>" >&2
    exit 2
    ;;
esac

echo "==> 1. lint       — approve prose rhythm, spoken form, and writing patterns"
python3 "$(dirname "$0")/lint_script.py" "$SOURCE"

echo "==> 2. segment    — derive one beat per approved prose paragraph"
if [ -n "$PROSE" ]; then
  python3 "$(dirname "$0")/segment_script.py" "$PROSE" "$SCENES"
else
  echo "    existing scenes.json retained (legacy scene-first input)"
fi

mkdir -p "$OUT/render"

echo "==> 3. storyboard — confirm each beat's say pairs with the right show before spending"
python3 - "$SCENES" <<'PY'
import json,sys
for i,b in enumerate(json.load(open(sys.argv[1]))["beats"]):
    print(f"  {i:02d}  SAY: {b['say']}")
    print(f"      SHOW: {b['show']['type']:8} {b['show'].get('path', b['show'].get('lines',''))}")
PY

echo "==> 4. render     — produce out/render/NN.png for each beat"
echo "    captures/diagrams/terminals → real screenshots or Mermaid; text → record_html.mjs;"
echo "    AI images → only for short B-roll. (This step is yours to wire to your sources.)"
echo "    example for a text card:"
echo "      node src/record_html.mjs 'src/kinetic.html#NO%20CAMERA|NO%20EDITOR' $OUT/render/00.mp4 1920 1080 4"

echo "==> 5. voice      — ONE continuous read + word timestamps   [\$ COSTS MONEY: the voice]"
echo "    rough cut?  use the FREE local Kokoro voice here and skip the cost until approved."
echo "      python3 src/tts.py $SCENES $OUT"

echo "==> 6. sync       — cut each visual to its cue word and enforce minimum dwell"
echo "==> 7. assemble   — frame-snap the visuals and mux the mono voice track"
echo "      bash src/assemble.sh $SCENES $OUT"

echo "==> 8. music      — drop an instrumental bed at $OUT/music.mp3  [Lyria/ElevenLabs: pennies]"
echo "==> 9. caption    — generate a word-timed .srt from $OUT/words.json"

echo
echo "Order matters; the only real cost is step 5. See README.md and AGENTS.md."
