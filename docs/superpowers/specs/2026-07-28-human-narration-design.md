# Making ghostreel narration sound human

**Status:** design, approved 2026-07-28
**Trigger:** a reference series — 7 episodes, ~45 min, built 2026-07-28 from a private client doc
set — had good content and robotic delivery. The content was right. The reading was not. Source
material and re-cut instructions are recorded outside this repo.

## The evidence

Measured across all seven episodes: 7,051 words, 712 sentences (sentences of 3+ words).
Calibrated against prose the repo owner actually wrote — `README.md`, `docs/the-method.md`,
`KNOWN-ISSUES.md`.

| metric | owner's prose | reference series |
|---|---|---|
| mean sentence length | 12.4 – 16.3 words | 9.7 |
| standard deviation | 6.2 – 8.0 | 4.7 |
| longest sentence | 33 – 34 words (in 70 tries) | 28 (in 712 tries) |
| sentences ≥ 20 words | 9 – 22% | 4% |
| sentences ≤ 6 words | 16 – 26% | 29% |
| connectives / 100 words | 3.5 – 5.6 | 4.7 |

The distinguishing signal is **long sentences**, not connectives. Connective density is normal;
the connectives are trapped inside short sentences instead of joining clauses. The owner writes
a 20-plus-word sentence about one time in seven. The series does it one time in twenty-five, and
its longest sentence across 712 attempts is shorter than his longest across 70.

An early hypothesis that the script lacked connective tissue did not survive measurement and was
dropped. The lint gates on length distribution only.

Audio, measured on `ep1.mp4` (402.8s):

- 156 pauses of ≥ 0.2s. Mean 0.49s, median 0.47s, **standard deviation 0.20**.
- 76.9s of silence — **19.1% of the runtime**.
- Pause length is near-uniform. Human speech varies pause length by syntactic boundary.

## Root causes

Three independent causes. Fixing only the writing addresses roughly a third of the problem.

### 1. The schema forbids the fix

`AGENTS.md:18` defines a beat as `"say": "one spoken sentence"`. `AGENTS.md:29` forbids run-ons.
An agent obeying that contract *cannot* emit a long sentence or a subordinate clause. The writing
agent followed the contract correctly; the contract is wrong.

### 2. The free path violates the repo's own first rule

`src/tts_local.py:110-120` synthesizes each beat separately and concatenates the wavs. `README.md:135`
states the rule it breaks: *"One continuous read, not per-beat. Per-beat clips sound disjointed."*
The reference series was built on this path. Every beat therefore ends on falling sentence-final
intonation and is followed by a near-constant pause. This is the single largest contributor, and
it is independent of word choice.

### 3. Cue sync is broken

`src/assemble.sh:43` reads `w["word"]`. Both `src/tts.py:88` and `src/tts_local.py:119` write the
key as `"w"`. Cue-word cutting cannot fire on the shipped explainer path, so visuals cut on beat
boundaries — reinforcing the one-card-per-sentence lockstep.

## Design

### Beat becomes a paragraph

`say` holds one complete thought: two to five sentences. `cue` marks where inside it the visual
cuts. Single-sentence beats still validate, so every existing `scenes.json` keeps working. Dwell
minimums move from per-beat to per-visual.

```jsonc
{
  "say": "Recording and editing was never the interesting part, and it ate four to six hours of every video I made. Re-takes, color, audio, cutting out every stutter. So I stopped recording. The script became the whole video, and the edit became a diff.",
  "cue": "four to six hours",
  "show": { "type": "diagram", "path": "assets/time-breakdown.png" }
}
```

### Authoring goes prose-first

Narration is written and reviewed as continuous prose. A second pass segments it into beats and
attaches visuals. The script stays the source of truth; the storyboard becomes derived. This is
what stops the beat grid from shaping the sentences — the writer never sees the grid while writing.

### Writing rules live in the repo

The repo is public and `AGENTS.md` is the contract every assistant reads. Rules cannot depend on a
private global skill. `docs/writing-for-the-ear.md` is derived from the `no-ai-slop` skill but
specific to spoken narration, and `AGENTS.md` points at it as a required gate. The owner's personal
global skill remains a lint layer on top.

### Lint becomes real code

`src/run.sh:16` currently `echo`s the lint step. Replace with `src/lint_script.py`, which computes
the distribution above and fails outside the voice envelope.

Starting thresholds, calibrated from the owner's prose and **to be validated against the ep1 recut
before they are locked**:

- mean sentence length ≥ 12 words
- standard deviation ≥ 6.5
- ≥ 10% of sentences at 20+ words
- ≥ 1 sentence over 30 words per episode
- ≤ 25% of sentences at 6 words or fewer

Plus the `no-ai-slop` banned-word and banned-pattern checks. A test pins the arithmetic against a
known script so the thresholds cannot drift silently.

### Audio: one continuous read, varied pauses

`tts_local.py` joins the whole script into a single synthesis call, matching the paid path, and
derives beat boundaries from the returned audio rather than from per-beat file lengths. Pause
length then varies by boundary type instead of sitting flat at 0.47s.

Consequence to handle: word timings in `tts_local.py` are currently "spread evenly per beat."
Across a 2-to-5-sentence paragraph beat that approximation gets materially worse, so cue placement
needs a better estimate — proportional to syllable count rather than word index, or forced
alignment.

### Doc-set to series workflow

Does not exist in the repo. The seven reference episodes were improvised end to end, which is exactly
why the process needs redirection from the owner every time. Becomes a documented flow: source docs
in → series outline → per-episode prose scripts → storyboard → render.

### Voice selection and the sample gallery

54 Kokoro voices ship in `voices-v1.0.bin` and cost nothing:

| language | female | male |
|---|---|---|
| American English | 11 | 9 |
| British English | 4 | 4 |
| Spanish | 1 | 2 |
| French | 1 | 0 |
| Hindi | 2 | 2 |
| Italian | 1 | 1 |
| Japanese | 4 | 1 |
| Portuguese | 1 | 2 |
| Mandarin | 4 | 4 |

`KOKORO_VOICE` already selects one, but globally per run. Work:

- `./ghostreel.sh --voices` prints the table; `--sample <voice>` generates and plays a line locally.
- `AGENTS.md` instructs the assistant to offer the list and ask, not silently default to `am_michael`.
- Per-speaker voice selection, which unlocks the two-host format at zero cost.

**Sample gallery.** GitHub strips `<audio>` tags from README markdown on repo pages
([community#53410](https://github.com/orgs/community/discussions/53410)), so committed audio linked
from the README will not play inline. A generated `docs/voices/index.html` on GitHub Pages carries a
real player per voice, grouped by language and gender. The README links to it and keeps a plain
table of raw links as a fallback.

Format is **mp3 at 64kbps, not wav**. Measured: an 8-second sample is 389–424 KB as wav versus
66–71 KB as mp3. All 54 voices is ~3.6 MB of mp3 against ~21 MB of wav, in a repo that is currently
tiny, and wav buys nothing for a preview clip.

**Known cost of the 54-voice choice:** `lang` is passed straight through to the espeak phonemizer,
so each non-English voice needs both the correct espeak code and a sample line *written in that
language*. English text read by a Japanese voice produces garbage. This requires sourcing eight
translated sample lines. Documented rather than allowed to silently degrade the gallery.

### Two-host dialogue

Sequenced after the prose work, deliberately. Dialogue written under one-sentence beat rules would
produce two robots instead of one. Depends on per-speaker voice selection.

## Validation

Re-cut the reference episode through the new pipeline with the free Kokoro voice and listen against the
current one. Free, and it becomes the repo's regression fixture with the measured thresholds pinned.

Acceptance:

- ep1 recut lands inside the voice envelope above.
- Pause standard deviation rises meaningfully above 0.20; total silence drops below 19.1%.
- The owner prefers the recut on a blind listen.

## Non-goals

- Paid-voice changes. Everything here is validated on the free path.
- Re-cutting the other six episodes. ep1 alone answers whether the prose landed.
- Reworking the kinetic/visual engine.

## Issues to file

Ordered. Dependencies noted.

1. **Beat schema: allow a paragraph in `say`** — schema, validation, dwell logic. Blocks 2, 4, 10.
2. **Prose-first authoring flow** — write/review narration as prose, derive the storyboard. Needs 1.
3. **`docs/writing-for-the-ear.md` + `AGENTS.md` gate** — repo-local narration rules.
4. **`src/lint_script.py`** — real lint replacing the `echo` at `src/run.sh:16`, thresholds pinned by test. Needs 1, 3.
5. **One continuous read in `tts_local.py`** — fix the `README.md:135` violation. Independent; highest impact per unit of work.
6. **Pause shaping** — vary pause length by boundary type. Needs 5.
7. **Fix cue key mismatch** — `w["word"]` vs `"w"` at `src/assemble.sh:43`. Standalone bug, fix now.
8. **Doc-set → series workflow** — the missing repeatable process.
9. **Voice discovery + sample gallery** — `--voices`, `--sample`, `AGENTS.md` prompt, generated GitHub Pages gallery, 54 mp3 samples, 8 translated sample lines.
10. **Two-host dialogue format** — per-speaker voices, speaker-tagged beats, interleaved timing. Needs 1, 9.
11. **Validation: re-cut ep1** — regression fixture, threshold calibration. Needs 1–6.
