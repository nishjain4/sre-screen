---
name: gitea-pull-requests
description: "Inspect Gitea pull requests, diffs, changed files and commits; review merge safety; create or merge a PR only when explicitly requested."
---

# Gitea pull requests

| Tool | Function | Use when |
|---|---|---|
| `list_pull_requests` | Lists PRs filtered by state, page, or limit. | Inventory PRs or find a candidate; if multiple match, ask which one rather than guessing. |
| `get_pull_request` | Reads details for one PR number. | Inspect metadata, branches, state, and head SHA for an exact PR. |
| `get_pull_request_diff` | Reads the full unified PR diff. | Review source changes for an exact PR. |
| `get_pull_request_files` | Lists files changed by an exact PR. | Scope a review or locate changed files. |
| `get_pull_request_commits` | Lists commits belonging to an exact PR. | Inspect the PR's commit history. |
| `create_pull_request` | Creates a PR from a head branch to a base branch with title/body/draft options. | Only when explicitly asked to open a PR and the source and target branches are known. |
| `merge_pull_request` | Merges a PR using a chosen merge method and optional title/message. | Only when the user explicitly asks to merge the exact PR and merge method is known; verify the target and current review/CI evidence first. |

For a safety review, use the exact PR number or URL; inspect metadata, diff, changed files, commits, review records, and CI status for its head SHA when available. Report verified defects, failed checks, and missing evidence separately. A 404, green/mergeable metadata, missing checks, or no detected defect does not prove safety. Creating and merging change remote state; never do either as an implied consequence of a review.
