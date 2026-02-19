# Morgen CLI Issue Triage & Fix

Triage, plan, and fix issues from `ISSUES.md` using parallel sub-agents and git worktrees.

## Phase 1: Triage

Read `ISSUES.md` and extract all **Open** issues. For each issue, capture:
- Title, severity, category, description
- Whether a fix approach is already described
- Estimated complexity (S/M/L) based on files touched and risk

If `$ARGUMENTS` is provided, filter issues:
- `all` (default) — show everything open
- `bugs` / `features` / `performance` — filter by category
- `critical` / `high` / `medium` / `low` — filter by severity

Present a **triage summary table** to the user:

| # | Issue | Severity | Category | Size | Fix Approach |
|---|-------|----------|----------|------|-------------|

Ask the user which issues to work on (default: all). Wait for confirmation before proceeding.

## Phase 2: Brainstorm & Plan

For each selected issue, invoke the `superpowers:brainstorming` skill to explore the design space — especially for medium+ complexity or missing-feature issues. Quick bugs can skip brainstorming.

Then invoke `superpowers:writing-plans` to produce an implementation plan per issue.

Present the consolidated plan to the user. Each issue's plan should include:
- Files to modify/create
- Key design decisions
- Test strategy
- Dependencies between issues (if any — some issues may conflict on the same files)

**Dependency detection is critical.** If two issues modify the same file, they CANNOT be parallelized in separate worktrees without merge conflicts. Group dependent issues together or serialize them.

Wait for user approval of the plan before proceeding.

## Phase 3: Parallel Execution

For each **independent** issue (or group of dependent issues):

1. **Create a git worktree** using `superpowers:using-git-worktrees`:
   ```
   git worktree add .worktrees/fix-<issue-slug> -b fix/<issue-slug>
   ```

2. **Dispatch a sub-agent** (Task tool, `subagent_type: general-purpose`, `mode: bypassPermissions`) into that worktree to implement the fix. The sub-agent prompt should include:
   - The full issue description from ISSUES.md
   - The implementation plan from Phase 2
   - Instructions to install deps and run tests: `cd <worktree-path> && uv sync --all-extras && uv run pytest -x`
   - Instructions to run type checks: `uv run mypy src/`
   - Instructions to commit the fix with a conventional commit message

3. **Run sub-agents in parallel** using multiple Task tool calls in a single message — one per independent worktree.

For dependent issue groups, run them serially in a single worktree.

## Phase 4: Review & Merge

After all sub-agents complete:

1. **Review each fix** using `superpowers:requesting-code-review` — or invoke the `code:review` skill on each worktree's diff.

2. **Run full test suite** in each worktree to confirm nothing is broken:
   ```
   cd <worktree-path> && uv run pytest -x && uv run mypy src/ && uv run ruff check .
   ```

3. **Present results** to the user:
   - Per-issue: pass/fail, diff summary, test results
   - Recommend which branches to merge

4. **On user approval**, merge each branch back to master:
   ```
   git merge fix/<issue-slug> --no-ff -m "fix: <issue title>"
   ```
   Then clean up worktrees:
   ```
   git worktree remove .worktrees/fix-<issue-slug>
   git branch -d fix/<issue-slug>
   ```

5. **Update ISSUES.md**: Move resolved issues from Open to Resolved with today's date and commit hash.

## Phase 5: Commit & Wrap Up

After all merges:
- Commit the updated ISSUES.md
- Present a final summary of what was fixed

## Important Notes

- **Never force-push or rewrite history** on master
- **Always ask before merging** — present diffs first
- If a sub-agent fails, report the failure and let the user decide whether to retry or skip
- Keep worktrees under `.worktrees/` (already in `.gitignore`)
- Clean up ALL worktrees even if some fixes fail
