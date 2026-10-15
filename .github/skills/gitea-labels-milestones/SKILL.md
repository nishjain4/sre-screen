---
name: gitea-labels-milestones
description: "Inspect Gitea issue labels and milestones, or create classification/planning metadata when explicitly requested."
---

# Gitea labels and milestones

| Tool | Function | Use when |
|---|---|---|
| `list_labels` | Lists repository labels, optionally paginated and limited. | Inspect labels or find a label ID before applying one elsewhere. |
| `list_milestones` | Lists milestones filtered by state and limit. | Inspect open, closed, or all repository milestones. |
| `create_label` | Creates a label with name, hex color, and optional description. | Only when the user explicitly requests a new label and specifies its intended name/color. |
| `create_milestone` | Creates a milestone with title and optional description and due date. | Only when explicitly asked to create a milestone with the intended title and schedule. |

These tools inspect or create repository metadata; they do not edit issues or PRs. Creating labels/milestones is a remote mutation and requires explicit user authorization.
