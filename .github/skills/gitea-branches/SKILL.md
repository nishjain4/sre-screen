---
name: gitea-branches
description: "Read the remote Gitea branch inventory or inspect, create, or delete a branch when explicitly requested. Use for branch names and branch operations."
---

# Gitea branches

| Tool | Function | Use when |
|---|---|---|
| `get_branch` | Reads details and head commit for a named branch. | Verify a branch exists or inspect its head. |
| `list_branches` | Lists repository branches, optionally paginated and limited. | Inventory branch names or find a candidate branch. |
| `create_branch` | Creates a branch from an existing branch or ref. | Only when the user explicitly requests branch creation and names the new branch; verify the source ref. |
| `delete_branch` | Deletes a named repository branch. | Only when the user explicitly requests deletion and the exact branch is confirmed; check that it is not protected or otherwise needed. |

Never use local Git refs as evidence of remote branch state. Branch creation and deletion are mutations; confirm the exact branch and source/effect before acting.
