# AGENTS.md — guide for AI assistants

You are helping a human build a video with the *video as code* method. This file is the
machine-readable contract. Read `README.md` and `docs/the-method.md` first.

## The one rule

The `scenes.json` file is the source of truth. Everything is generated from it. When the
human wants a change, edit `scenes.json` and re-run — never hand-edit the output.

## Data model

A video is `{ "format", "aspect", "voice_id", "beats": [...] }`. Each beat:

```jsonc
{
  "say":  "one spoken sentence",          // required; goes into narration + captions
  "cue":  "verbatim substring of say",    // optional; cut the visual in on this word
  "show": {
    "type": "capture|diagram|terminal|text|image",
    "path": "assets/foo.png",             // for capture/diagram/terminal/image
    "lines": ["BIG", "WORDS"]             // for type:text kinetic cards
  }
}
```

## Pipeline order (do not reorder)

1. `lint` — script reads like the human; no run-ons, no AI-crutch phrases, no visual reused
   across two beats.
2. `storyboard` — emit a SAY | SHOW table; get human approval before spending money.
3. `render` — produce each beat's visual file. Captures/diagrams/terminals/HTML for
   anything with text. AI images ONLY for short emotional B-roll.
4. `voice` — ONE continuous TTS call for the whole script; keep the word timestamps.
5. `sync` — set each visual's window from the cue word; enforce min on-screen dwell
   (diagrams ≥5s, stills ≥4s).
6. `assemble` — ffmpeg, frame-snapped, mono voice track.
7. `music` — instrumental bed, low volume, under the whole thing.
8. `caption` — word-timed `.srt`; burn-in only for vertical shorts.

## Cost discipline

- Always build a **rough cut with a free local voice** (Piper) first. Let the human review
  flow and cuts. Only generate the paid voice after they approve.
- The voice is the only meaningful cost. Images and music are pennies. Never re-voice the
  whole script to fix one line — fix the text and re-voice just what changed if the tooling
  allows, or accept the rough cut for review.

## Never

- Never commit a `.env` or any real key (`sk_...`, `sk-...`, `AIza...`).
- Never AI-generate a diagram, code block, UI, or any labeled image.
- Never invent a price, URL, hour, or claim. Ask or leave it out.
- Never insert `<break>` tags to fix pacing — use sentence shape and whitespace.
- Never concatenate a stereo clip onto the mono voice track.

## Files to use

**Vertical reel (fastest path):** `./ghostreel.sh --rough <intake.json>` for a free preview,
then `./ghostreel.sh <intake.json>` for the paid final. It chains voice → images → music →
`build_kinetic.py` (kinetic.css/js engine) → `record_html.mjs` → ffmpeg → captions →
`cheatsheet.py`. Sample: `examples/intake.example.json`.

**Explainer (long-form):** `src/tts.py` (voice), `src/record_html.mjs` (HTML→mp4),
`src/assemble.sh` (assemble), `src/run.sh` (the whole order). Adapt them; keep the order.

**Keys:** read from the environment via direnv — `cp .envrc.example .envrc`, fill it,
`direnv allow`. Scripts error clearly if a key is missing. Never write keys into the repo.
