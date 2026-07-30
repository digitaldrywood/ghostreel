# From a document set to a video series

Use this workflow when the input is a directory or pull request full of Markdown and the
output should be several related explainer episodes. It sits before ghostreel's normal
lint → segment → storyboard → render pipeline. It does not replace or reorder that pipeline.

Keep private source documents and working artifacts outside this public repository. Do not
copy private titles, paths, prose, or source references into a ghostreel issue, commit, pull
request, fixture, or example. The names below are deliberately generic.

## The artifacts

Create one working directory for the series. These files make the decisions reviewable and
keep each pass from inventing its own process:

```text
series/
├── SOURCE-INVENTORY.md
├── SERIES-OUTLINE.md
├── WATCH-ORDER.md
├── episode-01/
│   ├── narration.md
│   ├── source-refs.txt
│   ├── scenes.json
│   └── ep01.txt
└── episode-02/
    └── ...
```

- `SOURCE-INVENTORY.md` records the input snapshot and gives every source a short id.
- `SERIES-OUTLINE.md` owns episode boundaries, running order, thesis, and source coverage.
- `narration.md` owns an episode's spoken words.
- `source-refs.txt` maps each narration paragraph to the source paragraphs that support it.
- `scenes.json` is generated from approved narration, then owns visuals and every rendering
  stage.
- `epNN.txt` is a generated, source-linked storyboard for quick review. Never fix it by hand.
- `WATCH-ORDER.md` is the audience-facing index for the approved running order.

The three Markdown planning files and the source-reference sidecars are authoring records.
Once an episode is segmented, `scenes.json` remains the source of truth for rendering, as
described in `AGENTS.md`.

## Approval gates

| Gate | Human approves | Work that must wait |
| --- | --- | --- |
| Series outline | episode count, boundaries, order, thesis, and coverage | episode scripts |
| Episode prose | the complete narration and its source map | segmentation and visual planning |
| Storyboard | every SAY, SHOW, cue, and source reference | rendering, voice, and assembly |

Approval is about the artifact's current revision. If an upstream decision changes, repeat
the affected downstream gate instead of relying on the old approval.

## 1. Intake the sources

Freeze the input before summarizing it. For a Git repository or pull request, record the
repository and exact commit under review. For a directory, record the snapshot or delivery
identifier available to the team. Do not silently mix later edits into the same inventory.

List every Markdown file; do not select only the files whose names look relevant:

```bash
SOURCE_ROOT=/path/to/source-docs
rg --files "$SOURCE_ROOT" -g '*.md' | sort
rg -n '^#{1,6} ' "$SOURCE_ROOT" -g '*.md'
```

For a pull request, inventory the changed Markdown against its stated base as well:

```bash
BASE_REF=origin/main
HEAD_REF=feature-branch
git diff --name-only "$BASE_REF...$HEAD_REF" -- '*.md'
git diff --stat "$BASE_REF...$HEAD_REF" -- '*.md'
```

Read the complete set, then create `SOURCE-INVENTORY.md` with this table:

```markdown
Input revision: <commit, pull-request head, or snapshot id>

| Id | Path | Purpose | Relevant sections | Coverage | Questions |
| --- | --- | --- | --- | --- | --- |
| S01 | guide.md | Introduces the subject | Overview; Setup | required | none |
| S02 | reference.md | Defines constraints | Limits | required | confirm one ambiguity |
```

Use the inventory to record contradictions, missing facts, repeated material, and material
that is deliberately out of scope. Ask about unresolved facts; never fill a gap with a
plausible claim.

Give source paragraphs stable locators in the form `S01#overview/P02`: source id, normalized
heading, and prose-paragraph number within that heading. `P02` means the second prose
paragraph after the heading, ignoring the heading itself. Keep the input revision beside the
inventory so a locator always points into a fixed snapshot.

Intake is complete when every Markdown file appears in the inventory and every unresolved
question is answered or explicitly excluded.

## 2. Propose the series outline

Group the material by a single teachable thesis per episode. Let the source coverage decide
the episode count. Do not choose a count first and stretch or compress the material to fit it.

Create `SERIES-OUTLINE.md` with the episodes in proposed watch order:

```markdown
| Episode | One-line thesis | Source ranges | Starts after | Hands off to | Excludes |
| --- | --- | --- | --- | --- | --- |
| 01 | <one claim the episode will establish> | S01#overview/P01-P04 | audience knows the goal | episode 02 | reference detail |
| 02 | <one claim the episode will establish> | S01#setup/P01-P05; S02#limits/P01-P03 | episode 01 | independent use | historical notes |
```

Add a coverage ledger below it. Every required source range belongs to an episode, and any
deliberate omission or repetition has a reason:

```markdown
| Source range | Episode | Decision |
| --- | --- | --- |
| S01#overview/P01-P04 | 01 | introduce once |
| S02#limits/P01-P03 | 02 | required constraint |
```

Read the outline across episode boundaries. Each thesis should be distinct, the order should
build rather than repeat, and the handoff from one episode should make the next episode useful.

**Stop for outline approval. Do not draft episode narration until a human approves the episode
count, boundaries, running order, thesis, and coverage ledger.** Record the approved input
revision in the outline. A boundary or thesis change sends the outline back through this gate.

After approval, create `WATCH-ORDER.md` from the outline. Keep the same order and thesis, with
links to each approved storyboard and finished episode as those artifacts become available.

## 3. Write and approve each episode as prose

Write `episode-NN/narration.md` as plain Markdown with one complete spoken thought per
paragraph. Do not add headings, source labels, visual directions, or a SAY/SHOW grid to the
narration. Follow `docs/writing-for-the-ear.md` across the complete episode.

At the same time, create `episode-NN/source-refs.txt`. It has one non-empty line for every
narration paragraph, in the same order. Separate multiple supporting paragraphs with a
semicolon:

```text
S01#overview/P02
S01#overview/P03; S02#limits/P01
S02#limits/P02
```

The reference identifies support for the thought; the narration does not need to quote the
source. Transitions still need the reference that supports the claim they carry. If a claim
has no source, resolve it or remove it instead of labeling it as sourced.

Run the narration gate:

```bash
python3 src/lint_script.py series/episode-01/narration.md
```

Then read the joined narration aloud without visuals. Confirm that it proves the approved
thesis, stays inside the episode boundary, uses only supported claims, and sounds like one
continuous performance.

**Stop for prose approval. Do not create `scenes.json`, assign visuals, or show a storyboard
until a human approves both `narration.md` and its paragraph-for-paragraph source map.** A prose
change requires another lint run and prose approval.

## 4. Segment and storyboard

Segment the approved narration. The command creates placeholder visuals on the first run and
preserves compatible visual assignments on later runs:

```bash
python3 src/segment_script.py \
  series/episode-01/narration.md \
  series/episode-01/scenes.json
```

Replace each placeholder in `scenes.json` with one unique visual assignment. Use real captures,
diagrams, terminals, or HTML for anything containing text. Use AI images only for short,
unlabeled emotional B-roll. Add a verbatim `cue` when the visual should enter partway through
the spoken thought.

Generate the source-linked `epNN.txt` review artifact from `scenes.json` and the sidecar. This
command fails if the number of source-reference lines does not match the number of beats:

```bash
SCENES=series/episode-01/scenes.json
SOURCE_REFS=series/episode-01/source-refs.txt
STORYBOARD=series/episode-01/ep01.txt
python3 - "$SCENES" "$SOURCE_REFS" > "$STORYBOARD" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    beats = json.load(handle)["beats"]
with open(sys.argv[2], encoding="utf-8") as handle:
    refs = [line.strip() for line in handle if line.strip()]

if len(beats) != len(refs):
    raise SystemExit(f"source map has {len(refs)} entries for {len(beats)} beats")

for number, (beat, source) in enumerate(zip(beats, refs), start=1):
    print(f"CARD {number:02d}")
    print(f"SOURCE: {source}")
    print(f"SAY: {beat['say']}")
    if beat.get("cue"):
        print(f"CUE: {beat['cue']}")
    print("SHOW: " + json.dumps(beat["show"], ensure_ascii=False, sort_keys=True))
    print()
PY
```

Skim `epNN.txt` instead of watching a render. Confirm every card has the right source, the SAY
matches the approved prose, the SHOW advances that thought, cues are verbatim, and no visual is
reused. Fix narration in `narration.md`; fix visual assignments in `scenes.json`; update source
mapping in `source-refs.txt`; then regenerate the dump. Never edit `epNN.txt` directly.

**Stop for storyboard approval. Do not render visuals or generate a voice until a human approves
the complete source-linked storyboard.**

## 5. Hand each episode to the existing pipeline

Once the storyboard is approved, run the explainer pipeline map with the same approved inputs:

```bash
bash src/run.sh \
  series/episode-01/narration.md \
  series/episode-01/scenes.json
```

Follow the printed stages and `AGENTS.md` in order. Before the first rough cut, list and audition
the available local voices with `./ghostreel.sh --voices` and `./ghostreel.sh --sample <voice>`,
then ask the human to choose. Build the free local-voice rough cut, review it end to end, and use
the paid voice only after that approval.

Update `WATCH-ORDER.md` as episodes are approved and rendered. Its episode order must continue to
match `SERIES-OUTLINE.md`; rendering completion is not a reason to change the editorial order.

## Change control

Work back from the artifact that changed:

- A source revision invalidates the inventory locators. Refresh the inventory and coverage
  ledger, then reapprove every affected outline and episode.
- An episode boundary or thesis change returns to series-outline approval before prose changes.
- A narration or source-map change returns to prose approval, lint, segmentation, and storyboard
  approval.
- A visual or cue change stays in `scenes.json` but still requires a regenerated and reapproved
  storyboard.
- A rendering defect is fixed in its source input or pipeline code and regenerated. Never patch a
  rendered file or `epNN.txt`.

The process is complete when `WATCH-ORDER.md` matches the approved outline, every narration
paragraph has a source reference, every episode has an approved `epNN.txt`, and each approved
storyboard has entered the existing pipeline without skipping an approval gate.
