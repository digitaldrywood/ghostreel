# AGENTS.md — guide for AI assistants

You are helping a human build a video with the *video as code* method. This file is the
machine-readable contract. Read `README.md`, `docs/the-method.md`, and
`docs/writing-for-the-ear.md` first.

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

1. `lint` — apply `docs/writing-for-the-ear.md` to the complete narration, not isolated
   beats. The script must pass its rhythm, banned-word, banned-pattern, and spoken-form
   checks before storyboard; also reject run-ons and visuals reused across two beats.
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

- Always build a **rough cut with the free local voice first** (`src/tts_local.py` —
  Kokoro-82M, near-human, $0; falls back to Piper if Kokoro isn't installed). Let the
  human review flow and cuts. Only generate the paid voice after they approve.
- The paid voice is the only meaningful cost. Images and music are pennies. Never re-voice
  the whole script to fix one line — fix the text and re-voice just what changed if the
  tooling allows, or accept the rough cut for review.

## Never

- Never commit a `.env`/`.envrc` or any real key (`sk_...`, `sk-...`, `AIza...`).
- Never AI-generate a diagram, code block, UI, or any labeled image.
- Never invent a price, URL, hour, or claim. Ask or leave it out.
- Never insert `<break>` tags to fix pacing — use sentence shape and whitespace.
- Never concatenate a stereo clip onto the mono voice track.

## Files to use

**Vertical reel (fastest path):** `./ghostreel.sh --rough <intake.json>` for a free preview,
then `./ghostreel.sh <intake.json>` for the paid final. It chains voice → images → music →
`build_kinetic.py` (kinetic.css/js engine) → `record_html.mjs` → ffmpeg → captions →
`cheatsheet.py`. Sample: `examples/intake.example.json`.

**Local rough voice:** `src/tts_local.py` — Kokoro-first (KOKORO_DIR, default
`~/.local/share/kokoro-tts`; KOKORO_VOICE, default `am_michael`), Piper fallback
(PIPER_BIN + PIPER_VOICE). Same output contract as the paid `src/tts.py`, so the rest of
the pipeline doesn't care which one ran.

**Explainer (long-form):** `src/tts.py` (voice), `src/record_html.mjs` (HTML→mp4),
`src/assemble.sh` (assemble), `src/run.sh` (the whole order). Adapt them; keep the order.

**Keys:** read from the environment via direnv — `cp .envrc.example .envrc`, fill it,
`direnv allow`. Scripts error clearly if a key is missing. Never write keys into the repo.

## Filing an issue for the orchestrator

When you discover out-of-scope work, file it as a separate issue rather than
widening the one you are on. End the body with a `detent-agent` block so the
orchestrator can size it:

```detent-agent
schema: 1
effort: low
```

`effort` must be exactly one of `low`, `medium`, `high`, `xhigh`, `max`, or
`ultra`. Plausible-sounding values like `small`, `trivial`, or `xs` are rejected
by the backend and stall the whole project's preflight until a human edits the
issue body. Omit the key entirely to inherit the project default.

Size by how much reading the work needs, not by diff size:

- `low` — one file, contract already stated in the issue (a key mismatch, a
  wrong path, a docs edit).
- `medium` — a few files that must agree, or a change needing a new test.
- `high` — the beat schema, TTS timing, or cue-sync engine, where the fix has to
  hold across the whole pipeline order.
- `xhigh` and above — reserve for work that has to re-derive the measured
  baseline (sentence distribution, pause statistics) before it can be judged.
