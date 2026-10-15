# Gitea Repository Investigator — HTTP API

Base path: `/api`. All timestamps are ISO-8601 UTC (`2026-10-13T10:00:00Z`).
The canonical model definitions live in [`backend/app/schemas.py`](../backend/app/schemas.py).

If the backend runs with `API_KEY` set, every request must send `X-API-Key: <key>`
(the SSE endpoint also accepts `?api_key=<key>` because `EventSource` cannot set headers).
`X-Forwarded-User` (set by an SSO proxy) is recorded as `initiated_by`.

## Catalog

| Method | Path | Response |
|---|---|---|
| GET | `/api/health` | `{status: "ok", version}` |
| GET | `/api/config` | `ServiceConfig` — LLM, orchestrator, and Gitea MCP server status |
| GET | `/api/skills` | `SkillInfo[]` |
| GET | `/api/tools` | `ToolInfo[]` |
| GET | `/api/templates` | `TemplateInfo[]` |

Each `SkillInfo` includes `mcp_servers`, the MCP server name(s) associated with
its tools. Skills with no MCP-backed tools return an empty list.

## Investigations

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/investigations` | `InvestigationCreate` | `Investigation` (201, status `queued`) |
| GET | `/api/investigations?limit=50&offset=0&q=` | | `{items: InvestigationSummary[], total}` |
| GET | `/api/investigations/{id}` | | `Investigation` |
| DELETE | `/api/investigations/{id}` | | 204 |
| POST | `/api/investigations/{id}/cancel` | | `Investigation` |
| GET | `/api/investigations/{id}/events` | | `text/event-stream` (see below) |
| POST | `/api/investigations/{id}/chat` | `{message}` | `ChatMessage` (assistant reply) |
| POST | `/api/investigations/{id}/feedback` | `{helpful, comment?}` | `Feedback` |
| GET | `/api/investigations/{id}/export?format=markdown\|json` | | file download |

`InvestigationCreate`:

```json
{
  "query": "Summarize this Gitea repository",
  "mode": "auto",              // "none" | "specific" | "auto"
  "skill_ids": [],             // required (>=1) when mode == "specific"
  "context": {},  // optional Gitea request hints
  "template_id": null
}
```

## Server-Sent Events

`GET /api/investigations/{id}/events` streams named events. Every `data:` payload is JSON.

| event | data | Client action |
|---|---|---|
| `snapshot` | `Investigation` | Replace whole state (always first event) |
| `status` | `{status, outcome, title, selected_skill_ids, started_at, finished_at, duration_ms, error}` | Merge into investigation |
| `plan` | `InvestigationPlan` | Set `plan` |
| `step` | `InvestigationStep` | Upsert into `steps` by `id` (contains its tool calls) |
| `tool_call` | `{step_id, call: ToolCall}` | Upsert `call` by `id` inside the step's `tool_calls` |
| `timeline` | `TimelineEvent[]` | Replace `timeline` |
| `report` | `InvestigationReport` | Set `report` |
| `chat` | `ChatMessage` | Append to `chat` (dedupe by `id`) |
| `done` | `{status}` | Investigation finished; server closes the stream |

A comment line (`: ping`) is sent every 15 s as a keep-alive. When the investigation
is already finished the server sends `snapshot` followed immediately by `done`.

## Report structure

Every completed investigation has a `report` with these sections:

1. `executive_summary`
2. `root_cause` — `{summary, details, confidence: high|medium|low, category}`
3. `supporting_evidence` — `[{title, detail, source, severity}]`
4. `log_analysis` — `{summary, findings: [{pattern, count, level, first_seen, last_seen, sample, interpretation}]}`
5. `recommended_remediation` — `[{priority, action, rationale, command, risk, timeframe}]` (priority 1 = do first)
6. `next_steps` — `string[]`
7. `conclusion_summary` — Markdown closing summary: verdict, key finding, actual
   coverage, code findings, evidence limitations, and next action. Defaults to `""`
   for older stored reports; clients may fall back to `executive_summary`.

plus `title`, `severity`, `conclusive`, `affected_services`, `suggested_questions`, `generated_by`, `data_sources`.

`tool_results` is an additive `ToolCall[]` field (defaults to `[]` when reading older reports).
It preserves every diagnostic call's `id`, `tool`, `args`, `status`, `description`, `summary`,
`error`, `data_mode`, complete `output`, timestamps, and duration. The report UI shows these
under **MCP and Diagnostic Tool Results**; JSON and Markdown exports retain them as well.
Failed calls are not omitted or converted into successful/healthy findings.

Native targeted diagnostic runs include explicit request, routing, planning, execution,
coverage, correlation, analysis, remediation-safety, and publication stages in `steps`.
A bare repository link deterministically selects Gitea repository discovery and its ten-stage
read-only overview; focused PR/issue/commit requests are not widened. Repository reports remain
inconclusive about production availability and include inventory bounds and evidence gaps.
Each repository stage and each AI diff batch is a separate streamed and persisted trace
step. Tool calls belong to their actual stage, without duplication on the parent skill.
PR analysis includes exact-head source/test context (12 files, 16,000 characters per
file, 64,000 source characters total); clipping, permission errors, and missing tools
are explicit limitations, never passed checks.

