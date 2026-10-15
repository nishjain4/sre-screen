---
name: gitea-commits-status
description: "Inspect Gitea commit history, commit details and diffs, changed-file statistics, and CI statuses for a commit or resolved pull request head SHA."
---

# Gitea commits and status

| Tool | Function | Use when |
|---|---|---|
| `list_commits` | Lists commits, optionally for a branch/ref and page/limit. | Find recent commits or inspect history on a known ref. |
| `get_commit` | Reads details for a commit ref. | Inspect metadata for an exact SHA, tag, or branch ref. |
| `get_commit_diff` | Reads the unified diff for an exact commit ref. | Review source changes introduced by a known commit. |
| `get_commit_stats` | Reads commit details and per-file change statistics. | Summarize files changed and additions/deletions for an exact commit. |
| `get_commit_status` | Reads the combined status for a commit ref. | Check aggregate CI/status for a verified SHA. |
| `list_commit_statuses` | Lists individual statuses for a commit ref. | See individual CI checks and their results for a verified SHA. |

For a PR, resolve its head SHA from PR metadata before querying commit status; never check a guessed or base-branch SHA and present it as the PR's CI result. Commit reads are not proof that a deployment occurred.
