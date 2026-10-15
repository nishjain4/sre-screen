# Project Workflow

The application is a Gitea repository investigator. It keeps a small FastAPI/React shell around an HTTP Gitea MCP client and twelve focused repository skills.

## Request Path

1. The frontend loads Gitea templates, skills, tools, and runtime status through `/api`.
2. An investigation request is persisted by `InvestigationService`, then passed to the configured orchestrator.
3. The native orchestrator selects Gitea skills from the request or runs repository discovery for a repository overview.
4. Skills call registered `gitea__*` tools through `ToolExecutor`, which validates arguments, applies timeouts, records results, and streams progress.
5. Findings and tool output are assembled into a report and persisted. The frontend follows the event stream while the investigation is active.

## Gitea MCP

`backend/config/mcp_servers.yaml` connects to the bundled HTTP server at `http://localhost:8001/mcp`. Start `gitea_mcp/gitea_mcp_server.py` first and configure its `GITEA_URL` in `gitea_mcp/.env`. The client and manager live in `backend/app/integrations/mcp_servers/`; the optional in-process transport remains available. Configure the same `GITEA_URL`, plus `GITEA_OWNER`, `GITEA_REPO`, and `GITEA_TOKEN`, in `backend/.env`.

VS Code MCP configuration is optional and local only; it is not required by the application. Tool guidance is in [.github/skills/gitea/SKILL.md](.github/skills/gitea/SKILL.md).

## Main Modules

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI startup and Gitea MCP lifecycle |
| `backend/app/api/` | Health, configuration, skills, tools, templates, and investigations |
| `backend/app/core/` | Persistence, events, tool registration, and execution |
| `backend/app/orchestration/` | Investigation lifecycle, skill routing, evidence, reports, chat, and exports |
| `backend/app/skills/builtin/gitea_investigation.py` | Gitea repository skill set |
| `backend/app/skills/playbooks/gitea-pr-review/` | PR review guidance loaded by the review skill |
| `backend/config/mcp_servers.yaml` | Gitea MCP configuration |
| `backend/config/templates.yaml` | Gitea home-page templates |
| `automation/gitea_control.py` | Source-validation report polling and publication |

## Local Checks

From the repository root, `python automation/validate.py` runs static checks, backend/frontend builds, and offline startup health checks. Install the backend, MCP, and automation requirements and run `npm ci` in `frontend` first. Python 3.14 and Node.js 22 or newer are required; Docker is not. Test files/folders are not published; separately available local suites can be run with `--include-tests`.
