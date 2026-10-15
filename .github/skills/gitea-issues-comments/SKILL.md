---
name: gitea-issues-comments
description: "Read Gitea issue records and discussion, list issues, or create, update, and comment on an issue when explicitly requested."
---

# Gitea issues and comments

| Tool | Function | Use when |
|---|---|---|
| `list_issues` | Lists repository issues (excluding pull requests), with state/page/limit filters. | Find issues or inventory open/closed issues. |
| `get_issue` | Reads one issue by its exact number. | Inspect a specific issue. |
| `list_issue_comments` | Lists comments for an issue or pull request number. | Read the discussion on a known issue/PR. |
| `create_issue` | Creates an issue with a title and optional body, labels, and assignees. | Only when the user explicitly asks to open an issue. |
| `update_issue` | Updates an issue/PR title, body, state, or state reason. | Only when explicitly asked to edit or close/reopen the exact issue. |
| `add_issue_comment` | Adds a comment to an issue or pull request. | Only when explicitly asked to post a specified comment on the exact item. |

Issues and pull requests share a number space. Do not treat an issue number as a PR number or assume that one exists. Read-only inspection is distinct from posting or editing; mutations require an explicit request.
