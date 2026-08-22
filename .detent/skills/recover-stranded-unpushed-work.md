---
name: recover-stranded-unpushed-work
description: Recover prior Detent implementation work that was committed locally but never pushed and is no longer referenced by the current worktree.
when_to_use: Use when tracker history reports stranded unpushed commits, but the current Detent worktree is clean or has been recreated without those commits.
---

# Recover stranded unpushed work

Treat unreachable Git objects as evidence to review, not as changes to restore blindly. Do not run garbage collection before recovery; it can prune the only remaining copy.

Start with read-only discovery:

```bash
git status --short --branch
git reflog --all --date=iso --format='%h %gd %gs'
git fsck --no-reflogs --unreachable --no-progress
```

Inspect candidate commits by timestamp, parent, subject, changed paths, and full diff. A matching subject alone is insufficient because unreachable objects can belong to other worktrees or issues.

```bash
CANDIDATE="${CANDIDATE:?set CANDIDATE to the full commit SHA}"
git show -s --format='%H|%P|%ad|%s' --date=iso "$CANDIDATE"
git show --stat "$CANDIDATE"
git show "$CANDIDATE"
```

Compare the candidate's parent and hunks with current `origin/main`. Port only in-scope hunks onto the current base, preserve unrelated current changes, and re-run every required validation rather than relying on the stranded commit's old results. Before publishing, inspect the recovered diff for secrets or private material.

Once validation is green, commit and push the recovered work in the same session when possible. Confirm the remote branch or pull request points at the exact local head so the work cannot become stranded again.
