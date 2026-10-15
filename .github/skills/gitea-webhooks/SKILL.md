---
name: gitea-webhooks
description: "List Gitea repository webhooks or create/delete a webhook when explicitly requested. Use for webhook configuration questions."
---

# Gitea webhooks

| Tool | Function | Use when |
|---|---|---|
| `list_webhooks` | Lists repository webhooks. | Inspect configured webhook destinations/events when the returned data and permissions allow. |
| `create_webhook` | Creates a webhook from a type, configuration, event list, and active flag. | Only when the user explicitly asks to configure a webhook and supplies/ confirms endpoint configuration and events. |
| `delete_webhook` | Deletes a webhook by ID. | Only when explicitly asked to remove the exact webhook; verify its ID and identity first. |

Webhook configuration can contain sensitive destinations or secrets. Do not expose secret values in responses. Creating/deleting hooks changes remote behavior and requires explicit authorization.
