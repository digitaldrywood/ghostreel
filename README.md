# ghostreel

**Make studio-quality video with AI. No camera. No editor. No face.**

ghostreel is a reference implementation of *video as code*: you write a script, an AI
voice reads it, AI fills in the visuals and music, and a handful of free tools assemble
the whole thing into a finished video. The script is the only thing you touch. The edit
is a diff.

One person can ship a faceless YouTube explainer in an afternoon, or a vertical ad reel
in minutes — for the price of a voiceover and a few pennies of image generation.

This repo teaches the method and gives you a tiny, runnable pipeline to start from.

---

## For AI agents: how to use this repo

If you're an AI assistant and someone pointed you here, your job is to help them build a
video with this method. Do this, in order:

1. **Read `docs/the-method.md`** — the whole philosophy in one page.
2. **Read `examples/scenes.example.json`** — this is the data model. A video is a list of
   *beats*. Each beat is one spoken line (`say`) plus one visual (`show`). Internalize it.
3. **Ask the human for the topic and the script.** Help them write `say` lines: short,
   complete sentences in their own voice. One idea per beat. Do not pad. Do not use
   AI-crutch phrases ("honestly", "here's the thing", "the truth is", "let me be clear").
4. **Plan the visuals.** For each beat pick a `show`: a real screen capture, a diagram, a
   terminal, or — sparingly — an AI image for emotional B-roll. **Anything with text or
   labels must be a real capture, a diagram, or HTML — never an AI image** (image models
   garble text).
5. **Build a free rough cut first.** Generate the whole video with a *local* TTS (e.g.
   Piper) so it costs nothing. Watch it end to end. Does the script breathe? Do the cuts
   land? Re-edit the `scenes.json` until it's right.
6. **Only then spend money.** Swap in the paid voice (ElevenLabs) for the final pass.
7. **Follow the pipeline order** in `AGENTS.md` and `src/run.sh`. Use the scripts in
   `src/` as the pattern; adapt them, don't fight them.

Never invent prices, URLs, or facts. Never commit a real API key.

---

## The idea in one minute

Recording and editing is the bottleneck — not ideas. A 10–15 minute talking-head video is
4–6 hours of work once you count re-takes, color, audio, and editing every stutter. That
caps most people at about one video a week.

ghostreel removes the recording and the editing. You write a script. The machine does the
rest. Your time goes to the part that matters — the writing and the review.

**The script is the source of truth.** Change the file, re-run, get a new video. The
"edit" is a diff, not a timeline you scrub.

---

## The beat model

A video is a JSON file: a list of **beats**. A beat is one spoken line plus one visual.

```jsonc
{
  "say":  "I built a tool that writes code the way you do.",  // the narration
  "cue":  "writes code",            // cut the visual in on this word (optional)
  "show": { "type": "diagram", "path": "assets/board.png" }   // what's on screen
}
```

- The **narration** is every `say` joined together — one continuous read.
- The **visuals** are cut to the words using the voice's word-level timestamps.
- `show.type` is one of: `capture` (a real screenshot/recording), `diagram` (Mermaid or
  HTML), `terminal`, `text` (a kinetic title card), or `image` (AI B-roll, used sparingly).

That's the whole format. See `examples/scenes.example.json`.

---

## The pipeline

```
scenes.json
   │
   ├─ lint        sanity-check the script (your voice, no run-ons, no recycled visuals)
   ├─ storyboard  print a SAY | SHOW table and approve it before spending anything
   ├─ render      build each beat's visual (capture / diagram / terminal / image)
   ├─ voice       ONE continuous TTS read with word-level timestamps  ← the only real cost
   ├─ sync        cut each visual to its cue word; enforce a minimum on-screen dwell
   ├─ assemble    ffmpeg stitches visuals to the voice track (frame-snapped)
   ├─ music       a low instrumental bed under the whole thing
   └─ caption     word-timed .srt (or burned-in captions for vertical shorts)
        │
        ▼
     final.mp4
```

Two flavors fall out of the same pipeline:

| | **Ad reel** (vertical) | **Explainer** (faceless YouTube) |
|---|---|---|
| Shape | 1080×1920, ~30s | 16:9 (or 9:16 short), 7–15 min |
| Goal | sell a product | teach something |
| Voice | a catalog voice | your own cloned voice |
| Visuals | kinetic type + product photos | diagrams, captures, terminals |
| Script | a flat list of lines | a structured `scenes.json` |

---

## What it costs

| Tool | Role | Cost |
|---|---|---|
| **ElevenLabs** (or any TTS) | the voice | the only real cost — a subscription |
| **gpt-image** / image API | B-roll art | pennies per image |
| **Lyria** / music API | the music bed | free tier / pennies |
| **ffmpeg** | all video & audio | free, open source |
| **Playwright** | record HTML animations | free, open source |
| **Piper** | free local voice for rough cuts | free, open source |
| **Python / bash** | glue | free |

A ~30-second short runs about **$0.25–0.35 pay-as-you-go** (a real test run came to $0.33),
dominated by the images. A long explainer is a few dollars of voice. The pipeline is free.

The move that keeps it cheap: **rough-cut with a free local voice, approve, then pay once.**

---

## Hard-won rules (read these — they cost real time to learn)

- **One continuous read, not per-beat.** Send the whole script to the TTS in one call and
  use the returned word timestamps to cut visuals. Per-beat clips sound disjointed.
- **Pace with whitespace, not break tags.** One sentence per line, a blank line between
  beats. Fighting the model with `<break>` tags sounds halting.
- **Audio is mono.** Don't splice a stereo clip in front of a mono voice track — it
  garbles. Force every audio input to mono before concatenating.
- **Validate every visual by eye.** Never trust a filename or a thumbnail. Open it and
  confirm it matches the line being spoken at that second.
- **Never AI-generate anything with text/labels.** Diagrams, code, UI → real captures,
  Mermaid, or HTML. AI images are for short emotional B-roll only.
- **Rough cut free, final paid.** Review with a local voice before you spend a cent.
- **Master high-res.** For YouTube, render at 1440p+ so it lands in the higher bitrate
  tier; text stays crisp.

---

## Quickstart (human)

You need `python3`, `node`, and `ffmpeg` on PATH.

```bash
npm install                 # installs Playwright + Chromium (for recording HTML)
cp .envrc.example .envrc     # fill in your API keys, then:
direnv allow                 # (or, without direnv:  set -a; source .envrc; set +a)

# 1) FREE preview — local robot voice, placeholder cards. Costs nothing. Watch the flow.
./ghostreel.sh --rough examples/intake.example.json

# 2) When it's right, the paid final — real voice + AI images + music (~$0.25–0.35):
./ghostreel.sh examples/intake.example.json
```

Out comes `out/<title>/short.mp4`, a word-timed `short.srt`, and a `cheatsheet.html`
receipt that adds up exactly what the run cost. Edit `examples/intake.example.json` (or
write your own) to change the video — that's the whole interface.

For the long **explainer** flavor (faceless YouTube, diagrams/captures), see
`src/run.sh` and `examples/scenes.example.json`.

> **Dogfood:** this is the same pipeline used live in the "Video as Code" conference talk —
> the audience picks a theme, ghostreel builds the short while the speaker talks, and the
> `cheatsheet.html` shows the real cost. What you clone is what runs on stage.

---

## Repo layout

```
README.md                    you are here
AGENTS.md                    machine-readable guide for AI assistants
docs/the-method.md           the philosophy, one page
ghostreel.sh                 one command: intake.json → finished vertical short + receipt
examples/intake.example.json a fun 6-beat sample reel (theme → short)
examples/scenes.example.json a tiny sample explainer (long-form flavor)
src/tts.py                   ElevenLabs with-timestamps (one continuous read)  [paid]
src/tts_piper.py             FREE local voice for rough cuts (Piper)
src/images.py                gpt-image B-roll (sequential, retrying)            [paid]
src/music.py                 ElevenLabs Music instrumental bed                 [from plan]
src/build_kinetic.py         intake + timings → kinetic HTML (uses the engine below)
src/kinetic.css + kinetic.js the original MIT kinetic-typography + particle engine
src/fonts/                   bundled OFL display fonts (Anton, Bebas Neue)
src/record_html.mjs          record any HTML animation to mp4 (Playwright)
src/assemble.sh + run.sh     the explainer (long-form) flavor
src/cheatsheet.py            the cost receipt
.envrc.example               placeholder keys — copy to .envrc (gitignored)
package.json                 Playwright dependency
LICENSE                      MIT
```

The kinetic engine (`kinetic.css` / `kinetic.js`) is original and MIT — not lifted from any
proprietary kit — so you can ship whatever you build with it.

---

## Why "ghostreel"

Faceless video — a ghost behind the reel. You never appear; the work does.

Built by Cory LaNou / Drywood Creek Consulting · [www.digitaldrywood.com](https://www.digitaldrywood.com).
MIT licensed — take it, learn from it, ship your own.
