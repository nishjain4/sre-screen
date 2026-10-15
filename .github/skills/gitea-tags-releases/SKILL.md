---
name: gitea-tags-releases
description: "Inspect Gitea tags and releases, or create/delete a release only when explicitly requested. Use for version, tag, and release-note questions."
---

# Gitea tags and releases

| Tool | Function | Use when |
|---|---|---|
| `list_tags` | Lists repository tags, optionally paginated and limited. | Inspect version tags or locate a tag. |
| `list_releases` | Lists repository releases, optionally paginated and limited. | Inventory published/draft releases. |
| `get_release` | Reads a release by ID or tag. | Inspect one exact release. |
| `create_release` | Creates a release for a tag, with optional notes, target, draft, and prerelease settings. | Only when explicitly asked to publish or draft a release and the tag and intended settings are known. |
| `delete_release` | Deletes a release by numeric ID. | Only when explicitly asked to delete the exact release; verify its ID and identity first. |

Tags and releases are repository metadata, not proof of a deployment. Creating or deleting a release is a remote mutation and requires explicit user authorization.
