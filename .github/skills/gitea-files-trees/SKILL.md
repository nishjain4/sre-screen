---
name: gitea-files-trees
description: "Browse Gitea repository trees and read remote file contents at a branch, tag, or commit; create, update, or delete files only when explicitly requested."
---

# Gitea files and trees

| Tool | Function | Use when |
|---|---|---|
| `list_git_tree` | Lists files and directories at a tree/ref; can include descendants. | Browse the remote repository or locate a remote path. |
| `get_file` | Reads a text file at an optional branch, tag, or commit ref. | Inspect a known remote file path. |
| `get_file_content` | Reads and decodes a repository file at an optional ref. | Retrieve a file's content from the contents API. |
| `get_raw_file` | Reads raw file contents at an optional ref. | Retrieve exact raw remote source or text. |
| `create_file` | Creates a file with content, commit message, and optional branch. | Only when the user explicitly requests a new remote file. |
| `update_file` | Updates an existing file using its current blob SHA, content, and commit message. | Only when explicitly asked to modify a remote file; read its current SHA first. |
| `delete_file` | Deletes a file using its current blob SHA and commit message. | Only when explicitly asked to delete a remote file; verify path and SHA. |

Use remote tool output as repository evidence; local workspace content may differ. Create/update/delete operations commit remote changes and require explicit authorization for the exact path and branch.
