---
name: workflows
description: Inspect GitHub Actions workflows for this repo — list workflows, show recent runs, surface failing jobs and their logs. Use when the user types /workflows or asks "show CI status", "which workflows are failing", "what broke in the last run".
---

# /workflows — GitHub Actions inspector

When invoked, do these steps in order. Use the `mcp__github__*` tools if
available (preferred — typed API). Fall back to `gh` CLI via Bash if not.

## Step 1: Determine the repo

Read `git remote get-url origin` to extract `owner/repo`. If unsure, ask the user.

## Step 2: List configured workflows

Call `mcp__github__actions_list` with `method=list_workflows`. Print a compact
table: name, path, state.

## Step 3: Show recent runs (last 10)

Call `mcp__github__actions_list` with `method=list_workflow_runs`, `per_page=10`.
For each run, print: run id, workflow name, branch, status, conclusion (with
✅/❌ emoji), and event.

## Step 4: For each FAILED or CANCELLED run

- Note the run ID.
- Offer to fetch failed-job logs via `mcp__github__get_job_logs` with
  `run_id=<id>` and `failed_only=true`, `return_content=true`, `tail_lines=200`.

## Step 5: Summarize

End with a one-paragraph summary:

- How many workflows green / red.
- Which branches have problems.
- One concrete next action ("re-run X", "fix Y in Z.yml", "no action needed").

## Output rules

- Use a Markdown table for the runs list, not a numbered list.
- Don't dump full logs unless the user explicitly asks; show the failing step name and a 3–5 line excerpt.
- If `mcp__github__*` tools are missing, fall back to:
  - `gh workflow list`
  - `gh run list --limit 10`
  - `gh run view <id> --log-failed | tail -100`

## When NOT to use

If the user is asking about local script execution, npm scripts, or shell pipelines — not about CI. In that case, suggest the appropriate alternative.
