# AGENTS.md — guide for AI assistants

You are helping a human build a video with the *video as code* method. This file is the
machine-readable contract. Read `README.md`, `docs/the-method.md`, and
`docs/writing-for-the-ear.md` first.

## The one rule

The prose script owns the spoken words during authoring. After it passes lint,
`src/segment_script.py` updates `scenes.json`, which remains the source of truth for every
rendering stage. Change narration in the prose file, change visual assignments in
`scenes.json`, re-segment, and re-run. Never hand-edit downstream output.

## Data model

A video is `{ "format", "aspect", "voice_id", "beats": [...] }`. Each beat:

```jsonc
{
  "say":  "one complete spoken thought",  // required; one to five sentences
  "cue":  "verbatim substring of say",    // optional; cut anywhere inside the thought
  "show": {
    "type": "capture|diagram|terminal|text|image",
    "path": "assets/foo.png",             // for capture/diagram/terminal/image
    "lines": ["BIG", "WORDS"]             // for type:text kinetic cards
  }
}
```

`say` normally holds a paragraph of two to five sentences, but a single-sentence beat
remains valid. Keep one complete thought and one visual together; `cue` may match words
anywhere inside that paragraph.

## Pipeline order (do not reorder)

1. `lint` — apply `docs/writing-for-the-ear.md` to the complete prose script, not isolated
   paragraphs. The narration must pass its rhythm, banned-word, banned-pattern, and
   spoken-form checks before any visual grid exists.
2. `segment` — turn each approved prose paragraph into one beat, preserve matched visual
   assignments from an existing `scenes.json`, and reject visuals reused across beats.
3. `storyboard` — emit a SAY | SHOW table; get human approval before spending money.
4. `render` — produce each beat's visual file. Captures/diagrams/terminals/HTML for
   anything with text. AI images ONLY for short emotional B-roll.
5. `voice` — ONE continuous TTS call for the whole script; keep the word timestamps.
6. `sync` — set each visual's window from the cue word; enforce minimum dwell for each
   visual, independent of the beat's sentence count (diagrams ≥5s, stills ≥4s).
7. `assemble` — ffmpeg, frame-snapped, mono voice track.
8. `music` — instrumental bed, low volume, under the whole thing.
9. `caption` — word-timed `.srt`; burn-in only for vertical shorts.

## Cost discipline

- Before the first local rough cut, run `./ghostreel.sh --voices`, offer the available
  voice ids to the human, and ask which voice fits the video. Use
  `./ghostreel.sh --sample <voice>` to audition finalists, then set `KOKORO_VOICE` to the
  chosen id. Do not silently choose the `am_michael` default for them.
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
the pipeline doesn't care which one ran. `src/voices.py` owns the bundled voice catalog,
local audition command, correct language codes, and generated sample gallery.

**Explainer (long-form):** write paragraphs like `examples/narration.example.md`, run
`src/segment_script.py` to update the matching `scenes.json`, then use `src/tts.py`
(voice), `src/record_html.mjs` (HTML→mp4), `src/assemble.sh` (assemble), and `src/run.sh`
(the whole order). Adapt them; keep the order.

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
