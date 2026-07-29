#!/usr/bin/env bash
# run.sh — the end-to-end pipeline, in order. This is the map; each step is a real script
# you can run on its own. Read it top to bottom to understand the whole method.
#
#   bash src/run.sh examples/scenes.example.json
#
# Stages that cost money are marked. Build a free rough cut first, approve, then pay.
set -euo pipefail
SCENES="${1:-examples/scenes.example.json}"
OUT="out/$(basename "${SCENES%.json}")"
mkdir -p "$OUT/render"

echo "==> 1. lint     — does the script read like you? (do this by eye + your own linter)"
echo "    (keep it: varied sentence lengths, one complete thought per beat, no AI-crutch phrases)"

echo "==> 2. storyboard — confirm each beat's say pairs with the right show before spending"
python3 - "$SCENES" <<'PY'
import json,sys
for i,b in enumerate(json.load(open(sys.argv[1]))["beats"]):
    print(f"  {i:02d}  SAY: {b['say']}")
    print(f"      SHOW: {b['show']['type']:8} {b['show'].get('path', b['show'].get('lines',''))}")
PY

echo "==> 3. render   — produce out/render/NN.png for each beat"
echo "    captures/diagrams/terminals → real screenshots or Mermaid; text → record_html.mjs;"
echo "    AI images → only for short B-roll. (This step is yours to wire to your sources.)"
echo "    example for a text card:"
echo "      node src/record_html.mjs 'src/kinetic.html#NO%20CAMERA|NO%20EDITOR' $OUT/render/00.mp4 1920 1080 4"

echo "==> 4. voice    — ONE continuous read + word timestamps   [\$ COSTS MONEY: the voice]"
echo "    rough cut?  use a FREE local TTS (Piper) here and skip the cost until approved."
echo "      python3 src/tts.py $SCENES $OUT"

echo "==> 5/6. sync + assemble — cut visuals to the words, ffmpeg the final"
echo "      bash src/assemble.sh $SCENES $OUT"

echo "==> 7. music    — drop an instrumental bed at $OUT/music.mp3  [Lyria/ElevenLabs: pennies]"
echo "==> 8. caption  — generate a word-timed .srt from $OUT/words.json"

echo
echo "Order matters; the only real cost is step 4. See README.md and AGENTS.md."
