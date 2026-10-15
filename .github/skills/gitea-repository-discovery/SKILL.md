---
name: gitea-repository-discovery
description: "Inspect a Gitea repository's identity, metadata, languages, topics, and contributors. Use for repository overview, ownership, visibility, technology, or contributor questions."
---

# Gitea repository discovery

Use these tools for repository identity and descriptive inventory. Use the configured repository unless the user supplies a Gitea URL; never infer a different owner or repository from local files.

| Tool | Function | Use when |
|---|---|---|
| `get_repository` | Reads repository metadata, including name, description, default branch, and visibility. | Establish repository identity or answer metadata/visibility questions. |
| `get_repository_languages` | Reads language usage statistics. | The user asks what languages the repository uses. |
| `get_repository_topics` | Reads repository topics. | The user asks for repository topics or tags used for discovery. |
| `get_contributors` | Lists contributors, optionally paginated and limited. | The user asks who has contributed. |
| `get_contributor_stats` | Reads contributor activity statistics. | The user asks for contribution activity or relative contribution trends. |

For a broad repository overview, use `get_repository` first to confirm identity, then only the supporting inventory requested. For exact file, branch, commit, issue, or PR questions, use the corresponding category skill instead. These are reads; do not create or update repository metadata unless explicitly requested.
