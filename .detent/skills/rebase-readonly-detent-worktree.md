---
name: rebase-readonly-detent-worktree
description: Rebase a Detent worktree when shared remote refs or packed-refs are read-only, while preserving and proving the effective patch.
when_to_use: Use when a live base branch advanced, object writes are allowed, and ordinary fetch or rebase reports lock failures under the shared parent repository.
---

# Rebase a read-only Detent worktree

Keep the Detent-created worktree and branch. Do not create another worktree or reject the generated branch name.

1. Resolve the live base SHA through the repository API. Record the current head, merge base, binary patch, diff stat, and changed-file list under `$TMPDIR` before rebasing.
2. Fetch the base objects without depending on a writable remote-tracking ref:

   ```bash
   git fetch --no-write-fetch-head origin main
   git cat-file -t "$LIVE_BASE_SHA"
   ```

   A remote-ref lock warning is tolerable only when `git cat-file` proves the requested commit object arrived. Stop on any object-fetch failure.
3. While the Detent branch is checked out, rebase it without a third `<branch>` argument so `HEAD` stays attached:

   ```bash
   git rebase --onto "$LIVE_BASE_SHA" "$OLD_BASE_SHA"
   ```

4. Compare the post-rebase binary patch, diff stat, and changed-file list with the saved artifacts. Run `git range-diff` across the old and new commit ranges. Stop before pushing if any hunk or file changed without an explained conflict resolution.
5. If Git reports success but leaves a worktree-local cherry-pick marker because shared `packed-refs` is read-only, first prove that the worktree is clean and the Detent branch ref points at the verified rebased commit. Try `git cherry-pick --quit`. Only if that cleanup fails solely on the shared lock may you delete the worktree gitdir's `CHERRY_PICK_HEAD` marker with `apply_patch`, then switch back to the existing Detent branch. Never remove broader git state.
6. Revalidate the rebased head. Push with an explicit force-with-lease against the previously observed remote PR head because the local remote-tracking ref may be stale or unwritable:

   ```bash
   git push --force-with-lease="refs/heads/$BRANCH:$OLD_REMOTE_SHA" \
     origin "HEAD:refs/heads/$BRANCH"
   ```

7. Verify through the pull-request REST endpoint that its head SHA exactly matches `git rev-parse HEAD`, then rerun current-head CI and review checks.
