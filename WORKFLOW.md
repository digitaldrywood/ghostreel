You are working on {{ issue.identifier }}: {{ issue.title }}.
Current Detent status: {{ issue.state }}.

ghostreel is a public, MIT-licensed reference implementation of the "video as
code" method: a script file is the source of truth, an AI voice reads it, and a
small Python/shell/ffmpeg pipeline assembles a finished video. Read `AGENTS.md`
and `docs/the-method.md` before touching anything — `AGENTS.md` is the
machine-readable contract for this repo and it outranks your own instincts about
how a video pipeline should work.

Follow repository instructions, keep changes scoped to the issue, and keep a
single persistent `## Codex Workpad` issue comment updated with the plan,
validation evidence, and final handoff. Every Workpad update must include one
`detent-status` fenced block. Detent reads blocker and human-action
declarations from that block; narrative sentences are never read as blockers.
`status` must be one of `in_progress`, `blocked`, or `complete`.

## Repository Hard Rules

These are not style preferences. Violating any of them is a defect, and a
reviewer should send the issue back to `Rework`.

- **This repository is public and deliberately client-scrubbed.** Never
  introduce a client name, customer name, private document title, private
  project name, or real script content into code, comments, examples, fixtures,
  issue text, commit messages, or pull request bodies. Use the existing generic
  examples. If an issue seems to require private material to reproduce, treat
  that as a blocker and say so in the `detent-status` block instead of inventing
  or importing it.
- **Never commit a key or a key-bearing file.** No `.env`, no `.envrc`, no
  literal `sk_...`, `sk-...`, or `AIza...`. Keys come from the environment via
  direnv. `.envrc.example` is the only key-shaped file allowed in the tree.
- **`scenes.json` is the source of truth.** Everything is generated from it.
  Never hand-edit pipeline output to fix a problem; fix the input or the code
  that transforms it and re-run.
- **Do not reorder the pipeline.** The order in `AGENTS.md` is
  lint → storyboard → render → voice → sync → assemble → music → caption. A
  change that reorders these stages needs an explicit instruction in the issue.
- **One continuous TTS call for the whole script.** Per-beat synthesis is the
  bug behind ghostreel#8, not a valid implementation strategy. Keep the word
  timestamps from that single call; the rest of the pipeline depends on them.
- **Never AI-generate anything with text in it** — no diagrams, code blocks,
  UI, labeled images, or charts. Image models garble text. Real captures,
  diagrams, terminals, or HTML only. AI images are for short emotional B-roll.
- **Never insert `<break>` tags to fix pacing.** Use sentence shape and
  whitespace.
- **Never concatenate a stereo clip onto the mono voice track.**
- **Never invent a price, URL, runtime, model name, or capability claim.** The
  README and docs make concrete cost and quality claims; if a change would make
  an existing claim false, update the claim in the same pull request or leave
  the claim out.

## Project CI Quality Gates

This repository has **no CI workflow and no test suite** as of 2026-07-28: there
is no `.github/` directory and `main` is unprotected. That makes the local gate
and your own manual verification the only things standing between a bad change
and `main`. Treat that seriously rather than as permission to move fast.

Run the full local gate before moving an issue out of `In Progress`:

```sh
set -e
python3 -m compileall -q src
for f in ghostreel.sh src/*.sh; do bash -n "$f"; done
node --check src/record_html.mjs
for f in examples/*.json; do python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f"; done
```

| Stage category | Local command | CI check |
| --- | --- | --- |
| Python syntax (all of `src/`) | `python3 -m compileall -q src` | none — no CI configured |
| Shell syntax | `bash -n ghostreel.sh src/*.sh` | none — no CI configured |
| ESM parse (Playwright recorder) | `node --check src/record_html.mjs` | none — no CI configured |
| Example intake/scenes validity | `python3 -c "import json;json.load(open(F))"` per file | none — no CI configured |
| End-to-end rough cut (conditional) | `./ghostreel.sh --rough examples/intake.example.json` | none — no CI configured |

The gate above is cheap and static. It catches syntax and schema breakage; it
does **not** catch the class of bug that ghostreel#8 and ghostreel#9 describe —
dead air, per-beat synthesis, and cue-key mismatches all survive a syntax check.

Therefore: **if your change touches the beat schema, TTS, cue sync, timing,
assembly, or `ghostreel.sh` itself, you must additionally run the free rough cut
end to end and report its results in the Workpad.**

```sh
./ghostreel.sh --rough examples/intake.example.json
```

That path is free — it uses the local Kokoro voice (`src/tts_local.py`,
`~/.local/share/kokoro-tts`, `KOKORO_VOICE` defaults to `am_michael`) and
placeholder cards. It needs `ffmpeg`, `node`, and `python3` on PATH, plus
Playwright Chromium. If `node_modules` is absent in the
worktree, `ghostreel.sh` will symlink a borrowed tree when `GHOSTREEL_NODE_PATH`
is set; otherwise run `npm install`. If the rough cut genuinely cannot run in
your environment, say so explicitly in the Workpad — do not silently skip it and
report the static gate as if it were full validation.

When the rough cut is required, report these numbers in the Workpad, because
they are the acceptance signal for the current audio work:

```sh
# total silence and pause distribution
ffmpeg -hide_banner -nostats -i <out.mp4> -af "silencedetect=noise=-40dB:d=0.20" -f null - 2>&1 \
  | rg 'silence_duration' | awk '{print $NF}' \
  | python3 -c "
import sys, statistics
d = [float(x) for x in sys.stdin]
print('n', len(d), 'mean', round(statistics.mean(d),3), 'median', round(statistics.median(d),3),
      'sd', round(statistics.pstdev(d),3), 'total', round(sum(d),1))"
```

Do not rely on Detent or `detent doctor` to infer required stages or inspect CI
configuration. If you add a CI workflow as part of an issue, add its check name
to `gate.required_status_checks` in `detent.yaml` in the same pull request.

Use `in_progress` while implementation or validation is still active:

```detent-status
schema: 1
status: in_progress
blockers: []
human_action: null
```

Use `complete` only when the pull request is open, references the issue,
validation is green, and no actionable review comments remain:

```detent-status
schema: 1
status: complete
blockers: []
human_action: null
```

**This project runs autopilot.** Do not move a finished issue to `Human Review`
yourself. When the work is done, leave the issue in its current active state,
set the Workpad `detent-status` to `complete`, and stop. Detent evaluates the
configured gate and promotes the issue to `Merging` on its own. Moving the issue
to `Human Review` by hand parks it and defeats the gate.

An operator who wants a specific issue to stop for human eyes applies the
`requires-human-review` label to it; that is the opt-out, not a status move you
make on your own initiative.

For dependency blockers, use this order:

1. Create GitHub's native `blocked_by` dependency relation.

```sh
BLOCKED_NUMBER=<blocked-issue-number>
BLOCKER_NUMBER=<blocker-issue-number>
BLOCKER_ID="$(gh api repos/{owner}/{repo}/issues/$BLOCKER_NUMBER --jq '.id')"
gh api --method POST "repos/{owner}/{repo}/issues/$BLOCKED_NUMBER/dependencies/blocked_by" -F issue_id="$BLOCKER_ID"
```

2. Declare the blocker in the Workpad status block with `status: blocked`.

```detent-status
schema: 1
status: blocked
blockers:
  - ref: "owner/repo#123"
    reason: "waiting for the dependency to merge"
human_action: null
```

3. Legacy fallback during the deprecation window: if native dependencies are
   unavailable and the project has not migrated, keep a machine-readable
   issue-body line such as `Blocked by: #123` or `Depends on: owner/repo#123`.

If meaningful out-of-scope work is discovered, file a separate tracker issue in Backlog with a best-guess `detent-agent` effort block instead of expanding the current work item.

## Admission Criteria

### Alignment

- The issue improves this public, MIT-licensed video-as-code reference implementation,
  its generic examples and documentation, or the Detent configuration that dispatches
  work for this repository.
- The requested outcome preserves the script-first method and the pipeline invariants in
  `AGENTS.md`. Work that intentionally changes those invariants must say so explicitly.
- The issue is one independently useful change that belongs in this repository rather
  than a private production, client engagement, or unrelated tool.

### Readiness

- The issue states the desired outcome and observable acceptance criteria. A bug includes
  a generic reproduction or enough file and command context to reproduce it without
  private material.
- Required facts, prices, URLs, runtimes, model names, and capability claims have a
  verifiable source. The agent is not expected to invent or guess them.
- Dependencies are linked and terminal, and validation can run with the repository's
  documented local tools. Any required human choice, such as voice selection or
  storyboard approval, is identified before dispatch.

### Size

- The work fits one reviewable pull request and one primary outcome. Independent fixes,
  broad pipeline redesigns, and separately testable follow-ups are split into their own
  issues.
- The issue carries a `detent-agent` effort from the project rubric in `AGENTS.md`, sized
  by the amount of reading, coordination, and validation required rather than diff size.
- Work estimated above `xhigh` remains in Backlog until an operator explicitly assigns
  `max` effort and confirms the scope.

### Safety Gates

- Implementation and validation require no client names, customer data, private document
  titles, real production scripts, credentials, or key-bearing files in this public repo.
- Acceptance does not depend on paid voice, image, or music generation. Free local or
  static validation must be sufficient before any optional paid final run.
- The work preserves `scenes.json` as the generated source of truth, continuous TTS,
  mono assembly, pipeline order, and the ban on AI-generated text or labeled visuals
  unless the issue explicitly changes a named invariant with human approval.
- Destructive external actions, secret access, or unresolved product decisions keep the
  issue in Backlog until an operator supplies the missing authority or decision.

## Required Execution Flow

Use the current Detent state as the source of truth for which section applies.

Before any rebase, capture the branch's effective diff against its merge base
or preserve the pre-rebase ref. After the rebase, compare with `git range-diff`
or an equivalent diff-stat and confirm the same files and hunks remain. If
changes are missing without explanation or conflict resolution dropped hunks,
stop before pushing and move the issue to the configured blocked or exception
state.

### For Todo

1. Move the issue to `In Progress`.
2. Create or update the persistent `## Codex Workpad` comment with the plan,
   acceptance criteria, validation plan, and the `in_progress`
   `detent-status` block shown above.
3. Fetch current `origin/main`, confirm this worktree is based on it, and
   confirm every native dependency relation, `detent-status` blocker, and
   issue-body `Depends on:` reference is merged or otherwise terminal before
   coding.
4. Reproduce or confirm the reported behavior before changing code when the
   issue is a bug. For pipeline bugs this usually means running the free rough
   cut once before your change and once after, and reporting both.
5. Implement the smallest complete change that satisfies the issue.
6. Run the local gate, plus the rough cut when the change touches the beat
   schema, TTS, cue sync, timing, assembly, or `ghostreel.sh`.
7. Commit and push the branch.
8. Open or update a pull request that references the issue.
9. Re-check pull request comments, inline review comments, and CI after the
   latest push.
10. When the pull request is open, not a draft, references the issue, validation
    is green, and no actionable review comments remain, update the Workpad
    `detent-status` block to `status: complete` and leave the issue in its
    current active state. Do not move it to `Human Review`; Detent promotes it.

### For In Progress

1. Re-read the issue, pull request, comments, and `## Codex Workpad`, including
   the `detent-status` block.
2. Continue from the current repository and tracker state.
3. If implementation is complete, run the full pre-review gate, then update the
   Workpad block to `status: complete` with `blockers: []` and
   `human_action: null` and leave the issue in this state. Detent promotes on
   the configured gate.

### For Rework

1. Re-read all human and bot feedback.
2. Move the issue to `In Progress`.
3. Fix the requested changes.
4. Push updates to the pull request.
5. Run the full pre-review gate again.
6. Update the Workpad block to `status: complete` and leave the issue in its
   active state once the gate passes. Detent re-evaluates and promotes.

### For Merging

1. Confirm `$go-workflow:ship` is available in the Codex environment. If it is
   unavailable, keep the issue in `Merging` and record the missing ship workflow
   as `human_action` in the `detent-status` block.
2. Invoke and follow `$go-workflow:ship`.
3. Do not call `gh pr merge` directly outside the ship workflow.
4. End with exactly one terminal outcome:
   - pull request merged and issue moved to `Done`;
   - issue moved to `Rework` with an actionable defect;
   - issue remains in `Merging` with a concrete external blocker recorded in
     the `detent-status` block and described in the `## Codex Workpad`.
5. Move the issue to `Done` only after the pull request is merged.
