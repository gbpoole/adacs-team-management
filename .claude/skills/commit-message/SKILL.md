---
name: commit-message
description: Summarise recent changes as a one-line git commit message (≤25 words)
allowed-tools: Bash
---

Run `git diff HEAD` (and `git diff --cached` if relevant) to understand what changed, then write a single commit-message line that:

- Is 25 words or fewer
- Uses imperative mood ("Fix ...", "Add ...", "Remove ...")
- Covers all notable changes without padding

Output only the commit message line — no explanation, no bullet points, no quotes.
