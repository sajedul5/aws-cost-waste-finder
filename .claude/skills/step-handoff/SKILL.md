---
name: step-handoff
description: End-of-step handoff. Runs lint and tests, summarizes the changes, shows git status, and prints the exact git add/commit/push and gh pr create commands for the owner to run, then stops. Use when a plan step is finished.
---

# Step handoff

The owner does all commits, pushes, PRs and merges. You only prepare them.

1. **Lint and test** (skip a command if its tool isn't set up yet, and say so):
   ```sh
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/pytest
   ```
   If anything fails, fix it first. Report results honestly, with the failure output if any.

2. **Check docs**: CLAUDE.md plan checkbox for this step ticked; docs/ match the code.

3. **Safety check** on the diff: no account IDs (12-digit numbers), ARNs, access keys,
   real reports, or client data. `git diff main --stat` and `git status`.

4. **Summarize** in a few bullets: what changed and why, and anything left for later.

5. **Print the commands** for the owner, with the real branch name and specific file paths
   (not `git add .`):
   ```sh
   git add <files>
   git commit -m "<type>: <short summary>" -m "<body>"
   git push -u origin <branch>
   gh pr create --base main --title "<title>" --body "<body>"
   ```
   Use conventional-commit style (`feat:`, `chore:`, `docs:`, `test:`, `ci:`).
   End the commit message and PR body with the attribution lines from the current session's
   instructions, if any.

6. **From step 4 on**, also print the real-account test command for the owner:
   ```sh
   .venv/bin/cwf scan --region ap-southeast-1
   ```
   Remind them not to commit the output (`reports/` is gitignored).

7. **STOP.** Do not run any of those git/gh commands. Do not start the next step until the
   owner says "next".
