---
name: gitea-search
description: "Search Gitea repositories or commit history by text, branch/ref, path, author, or dates. Use when the user asks to find matching repositories or commits."
---

# Gitea search

| Tool | Function | Use when |
|---|---|---|
| `search_repository` | Searches Gitea repositories using a query and result limit. | Find repositories by name or search text; verify the returned repository before further operations. |
| `search_commits` | Searches commits with optional ref, path, author, date range, and result limit. | Find commits matching author/path/time or other supported commit filters. |

Search results may be incomplete or paginated; state the filters and bounds. Do not interpret an empty result as proof that no matching object exists beyond the searched scope.
