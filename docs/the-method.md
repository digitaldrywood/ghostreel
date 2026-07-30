# The method, one page

## The problem

Recording and editing is the bottleneck — not ideas. A 10–15 minute talking-head video
cost me 4–6 hours: setup, re-takes, color, audio, and editing out every stutter. I tried
the modern editors, and they helped, but not enough. I was capped at about one video a
week, and most of that time was mechanical work a machine should be doing.

## The shift

Stop recording. Make the **script** the whole video. Write the narration as prose first;
after it reads well on its own, derive the visual beats and let the machine read,
illustrate, and assemble them. Your time goes to writing and reviewing — the parts that
carry the message.

> The script is the source of truth. The edit is a diff.

Change a line, re-run, get a new video. There's no timeline to scrub and no footage to
re-shoot. If a sentence is wrong, you fix a sentence.

## The unit: a beat

Write one complete spoken thought per paragraph in a plain Markdown file. A thought
normally spans two to five sentences, while a single sentence remains valid. After the
complete prose passes review, segmentation turns each paragraph into a **beat** and joins
it to one visual. (`examples/narration.example.md` and `examples/scenes.example.json`.)

```jsonc
{ "say": "...", "cue": "concept word", "show": { "type": "diagram", "path": "..." } }
```

## The pipeline

1. **Lint** — make sure the complete prose reads like *you*: varied sentence lengths, one
   complete thought per paragraph, no filler, and no visual grid competing for attention.
2. **Segment** — derive one beat per approved paragraph while preserving compatible
   visual assignments from the prior storyboard.
3. **Storyboard** — print the SAY | SHOW pairs and approve them before spending anything.
4. **Render** — build each visual. Captures, diagrams, terminals, and HTML for anything
   with text; AI images only for short emotional B-roll.
5. **Voice** — send narrator scripts in one continuous read. For dialogue, send all turns
   for each of the two speakers in one speaker-level read, then interleave the aligned
   turns. Keep global word-level timestamps. This is the only step that really costs money.
6. **Sync** — cut each visual in on its concept word; hold it long enough to read.
7. **Assemble** — ffmpeg snaps the visuals to the voice on a frame grid.
8. **Music + captions** — a low instrumental bed and a word-timed caption track.

## The cost

Only the paid voice costs anything meaningful. Images are pennies, music is a free tier,
and ffmpeg/Playwright/Python are free. A short is about a quarter; a long explainer is a
few dollars.

The discipline that keeps it cheap: **rough-cut with a free local voice, watch it, fix it,
and only then pay for the final voice.** And that free voice is no longer a robot. My
first rough cuts used Piper — dependable, but you winced through the review. Now the local
pass runs **Kokoro-82M**, which sounds close to human, so the $0 cut is listenable enough
to judge pacing and flow for real. Piper stays as the fallback.

## The rules that cost me real time to learn

- One continuous narrator read, or one read per dialogue speaker, never per-beat —
  per-beat clips sound disjointed.
- Pace with sentence shape and whitespace between beats, never `<break>` tags.
- Force audio to mono before concatenating, or the track garbles.
- Validate every visual by eye against the line it's under.
- Never AI-generate text, labels, diagrams, code, or UI — those are real captures or HTML.
- Master at 1440p+ for YouTube so text lands in the higher-bitrate tier and stays crisp.

That's the whole method. The rest is taste.
