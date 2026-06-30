# The method, one page

## The problem

Recording and editing is the bottleneck — not ideas. A 10–15 minute talking-head video is
4–6 hours of work: setup, re-takes, color, audio, and editing out every stutter. Even good
editors (Descript and friends) only shave that down so far. Most people cap out at about
one video a week and burn out.

## The shift

Stop recording. Make the **script** the whole video. Write it as data; let the machine read
it, illustrate it, and assemble it. Your time goes to writing and reviewing — the parts that
actually carry the message.

> The script is the source of truth. The edit is a diff.

Change a line, re-run, get a new video. There's no timeline to scrub and no footage to
re-shoot. If a sentence is wrong, you fix a sentence.

## The unit: a beat

A video is a list of **beats**. A beat is one spoken line (`say`) and one visual (`show`).
String the `say` lines together and you have the narration. Attach a visual to each line
and you have the video. (`examples/scenes.example.json`.)

```jsonc
{ "say": "...", "cue": "concept word", "show": { "type": "diagram", "path": "..." } }
```

## The pipeline

1. **Lint** — make sure the script reads like *you*: short complete sentences, one idea per
   beat, no filler.
2. **Storyboard** — print the SAY | SHOW pairs and approve them before spending anything.
3. **Render** — build each visual. Captures, diagrams, terminals, and HTML for anything
   with text; AI images only for short emotional B-roll.
4. **Voice** — send the *whole* script to the TTS in one continuous read and keep the
   word-level timestamps. This is the only step that really costs money.
5. **Sync** — cut each visual in on its concept word; hold it long enough to read.
6. **Assemble** — ffmpeg snaps the visuals to the voice on a frame grid.
7. **Music + captions** — a low instrumental bed and a word-timed caption track.

## The cost

Only the voice costs anything meaningful. Images are pennies, music is a free tier, and
ffmpeg/Playwright/Python are free. A short is about a quarter; a long explainer is a few
dollars. The discipline that keeps it cheap: **rough-cut with a free local voice (Piper),
watch it, fix it, and only then pay for the final voice.**

## The rules that cost real time to learn

- One continuous read, never per-beat — per-beat clips sound disjointed.
- Pace with whitespace (one sentence per line), never `<break>` tags.
- Force audio to mono before concatenating, or the track garbles.
- Validate every visual by eye against the line it's under.
- Never AI-generate text, labels, diagrams, code, or UI — those are real captures or HTML.
- Master at 1440p+ for YouTube so text lands in the higher-bitrate tier and stays crisp.

That's the whole method. The rest is taste.
