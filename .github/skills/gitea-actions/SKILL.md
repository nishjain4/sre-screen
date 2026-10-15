---
name: gitea-actions
description: "Inspect Gitea Actions workflow definitions and run history, or dispatch a workflow when explicitly requested. Use for Gitea CI and workflow questions."
---

# Gitea Actions

| Tool | Function | Use when |
|---|---|---|
| `list_workflows` | Lists workflows configured in the repository. | Find available workflows or identify a workflow before inspecting runs. |
| `list_workflow_runs` | Lists workflow runs, optionally filtered by workflow ID/filename and page/limit. | Check recent run history or investigate failed/pending runs. |
| `trigger_workflow` | Dispatches a workflow for a specified workflow ID/filename and ref, with optional inputs. | Only when the user explicitly asks to run/dispatch a named workflow and supplies or confirms its ref and inputs. |

To investigate a run, identify the workflow and relevant run first; report status and missing evidence rather than inferring success. Dispatching changes remote state: never dispatch merely to investigate or because a workflow appears useful. Confirm the workflow, ref, and inputs before dispatch.
