#!/usr/bin/env bash
# ghostreel.sh — theme/intake -> finished vertical short + cost receipt.
# Self-contained: needs only this repo + your API keys + ffmpeg + node(playwright) + python3.
#
#   ./ghostreel.sh --rough intake.json   # FREE preview (local Kokoro voice, placeholder cards)
#   ./ghostreel.sh intake.json           # paid final (real voice + AI images + music)
#
# Keys come from the environment. Use direnv: `cp .envrc.example .envrc`, fill it, `direnv allow`.
# (If you don't use direnv, this script will also source ./.envrc when present.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

ROUGH=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--rough" ]; then ROUGH=1; else ARGS+=("$a"); fi
done
INTAKE="${ARGS[0]:-examples/intake.example.json}"
[ -f "$INTAKE" ] || { echo "no intake file: $INTAKE"; exit 1; }

# keys: prefer the environment (direnv); fall back to sourcing ./.envrc for non-direnv users
if [ -z "${ELEVENLABS_API_KEY:-}" ] && [ -f .envrc ]; then set -a; . ./.envrc; set +a; fi

need() { command -v "$1" >/dev/null || { echo "missing dependency: $1"; exit 1; }; }
need ffmpeg; need node; need python3; need convert
[ -d node_modules/playwright ] || [ -n "${GHOSTREEL_NODE_PATH:-}" ] || {
  echo "Playwright not installed. Run:  npm install"; exit 1; }
export NODE_PATH="${GHOSTREEL_NODE_PATH:-$HERE/node_modules}"

SLUG="$(python3 -c "import json,re,sys;t=json.load(open(sys.argv[1])).get('title','short');print(re.sub(r'[^a-z0-9]+','-',t.lower()).strip('-') or 'short')" "$INTAKE")"
RUN="out/$SLUG"; rm -rf "$RUN"; mkdir -p "$RUN/audio" "$RUN/assets"
cp "$INTAKE" "$RUN/intake.json"
echo "== ghostreel: $SLUG  (rough=$ROUGH) =="

# 1) voiceover  --------------------------------------------------------------
if [ "$ROUGH" = 1 ]; then
  echo "== 1/6 voice: FREE local rough cut (Kokoro; falls back to Piper) =="
  VO="$(python3 src/tts_local.py "$INTAKE" "$RUN")"
else
  echo "== 1/6 voice: ElevenLabs (continuous read)  [\$] =="
  : "${ELEVENLABS_API_KEY:?set ELEVENLABS_API_KEY}"
  VO="$(python3 src/tts.py "$INTAKE" "$RUN")"
fi
VO_CHARS="$(printf '%s\n' "$VO" | sed -n 's/^VO_CHARS=//p')"

# 2) images (skip in rough -> build uses placeholder cards)  -----------------
NIMG=0
if [ "$ROUGH" = 1 ]; then
  echo "== 2/6 images: skipped (rough cut uses placeholder cards) =="
else
  echo "== 2/6 images: gpt-image  [\$] =="
  : "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
  IMG_OUT="$(python3 src/images.py "$INTAKE" "$RUN" --size 1024x1536 --quality medium)"
  NIMG="$(printf '%s\n' "$IMG_OUT" | sed -n 's/^IMAGES=//p')"
  for f in "$RUN"/assets/img_*.png; do [ -f "$f" ] && convert "$f" -resize 1080x1920^ -strip -quality 88 "$f" 2>/dev/null || true; done
fi

# 3) build kinetic HTML + timeline  ------------------------------------------
echo "== 3/6 build kinetic HTML =="
BK="$(python3 src/build_kinetic.py "$INTAKE" "$RUN")"
DUR="$(printf '%s\n' "$BK" | sed -n 's/^DURATION=//p')"

# 4) music (skip in rough)  ---------------------------------------------------
MUS_SECS=0
HAVE_MUSIC=0
if [ "$ROUGH" = 0 ]; then
  echo "== 4/6 music: ElevenLabs Music  [\$ from plan] =="
  MPROMPT="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('music_prompt','upbeat instrumental'))" "$INTAKE")"
  MUS_SECS="$(awk "BEGIN{print ($DUR<10?10:$DUR)}")"
  python3 src/music.py --seconds "$MUS_SECS" --out "$RUN/audio/music.mp3" --prompt "$MPROMPT" && HAVE_MUSIC=1 || true
fi

# 5) record HTML -> mp4, then mux voice (+music)  ----------------------------
echo "== 5/6 record (Playwright) + mux (ffmpeg) =="
node src/record_html.mjs "$RUN/ad.html" "$RUN/ffx.mp4" 1080 1920 "$DUR"
FADE="$(awk "BEGIN{f=$DUR-1.5; print (f<0?0:f)}")"
if [ "$HAVE_MUSIC" = 1 ]; then
  ffmpeg -y -loglevel error -i "$RUN/ffx.mp4" -i "$RUN/audio/vo.mp3" -stream_loop -1 -i "$RUN/audio/music.mp3" \
    -filter_complex "[1:a]volume=1.0[v];[2:a]volume=0.18[m];[v][m]amix=inputs=2:duration=longest:dropout_transition=0,afade=t=out:st=${FADE}:d=1.5,loudnorm=I=-14:TP=-1.5:LRA=11[ao]" \
    -map 0:v -map "[ao]" -t "$DUR" -c:v copy -c:a aac -b:a 192k -movflags +faststart "$RUN/short.mp4"
else
  ffmpeg -y -loglevel error -i "$RUN/ffx.mp4" -i "$RUN/audio/vo.mp3" \
    -filter_complex "[1:a]afade=t=out:st=${FADE}:d=1.0,loudnorm=I=-14:TP=-1.5:LRA=11[ao]" \
    -map 0:v -map "[ao]" -t "$DUR" -c:v copy -c:a aac -b:a 192k -movflags +faststart "$RUN/short.mp4"
fi

# 6) captions + receipt  -----------------------------------------------------
echo "== 6/6 captions + cheatsheet =="
python3 - "$RUN/audio/words.json" "$RUN/short.srt" <<'PY'
import json,sys
W=json.load(open(sys.argv[1]))
ts=lambda t:f"{int(t//3600):02d}:{int(t%3600//60):02d}:{t%60:06.3f}".replace('.',',')
cues,cur=[],[]
for w in W:
    cur.append(w)
    if len(cur)>=7 or w["w"][-1:] in ".!?": cues.append(cur);cur=[]
if cur:cues.append(cur)
open(sys.argv[2],"w").write("\n".join(
  f"{i}\n{ts(c[0]['start'])} --> {ts(c[-1]['end'])}\n{' '.join(x['w'] for x in c)}\n"
  for i,c in enumerate(cues,1)))
print(f"srt -> {sys.argv[2]} ({len(cues)} cues)")
PY
TITLE="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('title','Short'))" "$INTAKE")"
THEME="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('theme',d.get('title','')))" "$INTAKE")"
python3 src/cheatsheet.py --out "$RUN/cheatsheet.html" --title "$TITLE" --theme "$THEME" \
  --chars "${VO_CHARS:-0}" --images "$NIMG" --imgsize 1024x1536 --imgquality medium \
  --music-seconds "$MUS_SECS" --duration "$DUR" --voice "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('voice_label','AI voice'))" "$INTAKE")"

echo
echo "DONE -> $RUN/short.mp4"
echo "       $RUN/cheatsheet.html   $RUN/short.srt"
[ "$ROUGH" = 1 ] && echo "(rough cut — review the flow, then run without --rough for the paid final)"
