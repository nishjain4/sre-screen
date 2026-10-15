# Gitea Repository Investigator

An investigation app for Gitea repositories, with focused repository, commit, issue, workflow, release, and pull-request skills.

## Repository Validation

The optional Gitea Actions validation reporter publishes check results and failure issues. See [Repository Validation](docs/REPOSITORY_VALIDATION.md) for its setup and permissions.

## Clone And Set Up Locally

Prerequisites: Git, Python 3.14, Node.js 22 or newer (including npm), and access
to your own Gitea instance and repository. AWS is optional. The Gitea MCP server
is bundled in `gitea_mcp/`; no other repository or VS Code extension is needed.

On Windows, run:

```powershell
git clone https://github.com/nishjain4/sre-screen.git
Set-Location sre-screen
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .\backend -r gitea_mcp\requirements.txt -r automation\requirements.txt
Copy-Item backend\.env.example backend\.env
Copy-Item gitea_mcp\.env.example gitea_mcp\.env
Copy-Item frontend\.env.example frontend\.env.local
Set-Location frontend
npm ci
Set-Location ..
```

Edit the copied environment files locally (never commit credentials):

| File | Required configuration |
| --- | --- |
| `gitea_mcp/.env` | Set `GITEA_URL` to your Gitea instance, for example `https://gitea.example.com`. |
| `backend/.env` | Set the same `GITEA_URL`, your `GITEA_TOKEN`, `GITEA_OWNER`, and `GITEA_REPO`. Keep `LLM_PROVIDER=offline` initially; no AWS credentials are needed. |
| `frontend/.env.local` | Defaults work locally. If backend `API_KEY` is set, set `VITE_API_KEY` to the same value. This key is visible to browser users; it is not a secret vault. |

Create a Gitea personal access token in your own instance under user settings,
Applications. Use read permissions for repository investigation; some APIs also
need issue/organization/user read scopes and access to private repositories.
Missing permissions appear as tool errors, not successful analysis.

### Start The Three Services

Use three terminals, each starting at the cloned repository root.

**Terminal 1 - local Gitea MCP server:**

```powershell
.\.venv\Scripts\Activate.ps1
python gitea_mcp\gitea_mcp_server.py
```

**Terminal 2 - backend (after the MCP server is listening):**

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 3 - frontend:**

```powershell
Set-Location frontend
npm run dev
```

Open <http://localhost:3000>. The Vite development server proxies `/api` and
`/docs` to `http://localhost:8000`. Keep all services local; the MCP HTTP endpoint
accepts Gitea tokens per request and is not intended for public exposure.

On macOS/Linux, use `python3.14 -m venv .venv`, activate with
`source .venv/bin/activate`, use `cp` instead of `Copy-Item`, and use `/` instead
of `\` in command paths. The Python/npm commands and configuration are otherwise
the same.

### Verify The Setup

After dependency installation, run from the root in the activated environment:

```powershell
python automation\validate.py
```

This checks Python static errors, builds the backend package and frontend
(including TypeScript checking), and runs real offline FastAPI startup, health,
and shutdown. Reports are written to ignored `validation-results/`. It works
without AWS, Gitea credentials, a running MCP service, or test folders. Test files
and folders are intentionally excluded from this repository; these checks are
not a replacement for a full unit/integration suite.

For a live end-to-end check, with all three services running:

1. Open <http://localhost:8000/api/health> and confirm `status` is `ok`.
2. Open <http://localhost:8000/api/config> and confirm the `gitea` MCP connection
   succeeded; <http://localhost:8000/api/tools> should list Gitea tools.
3. In the UI, paste a repository URL on your configured Gitea instance and
   request a repository overview. Confirm real repository metadata and tool
   outputs appear. Token/permission or connection errors must be resolved;
   tool discovery alone does not verify Gitea access.

If API-key authentication is enabled, use the UI or send `X-API-Key` when
checking protected endpoints. See [Local MCP setup](gitea_mcp/README.md) for
standalone MCP verification.

## Configuration

Copy `backend/.env.example` to `backend/.env`. The important settings are:

| Setting | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `bedrock` (example uses `offline`) | Selects Amazon Bedrock; use `offline` to force deterministic analysis. |
| `BEDROCK_MODEL_ID` | `eu.amazon.nova-lite-v1:0` | Bedrock model ID enabled in your AWS account and region. |
| `AWS_REGION` | `us-east-1` (example uses `ap-south-1`) | Region for Bedrock Runtime; choose one that supports your model. |
| `AWS_PROFILE` | empty | Optional AWS shared-credentials profile. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | empty | Optional AWS credentials; boto3 also supports its normal credential chain, including IAM roles. |
| `AWS_SESSION_TOKEN` | empty | Optional session token when using temporary AWS credentials. |
| `ORCHESTRATOR` | `native` | Selects the registered orchestrator, for example `native` or `external_example`. |
| `LLM_MAX_CONTEXT_CHARS` | `16000` | Follow-up chat context budget. Report synthesis includes all collected findings, logs, timeline events, and tool traces. |
| `MAX_AUTO_SKILLS` | `8` | Maximum relevant skills selected automatically for an investigation. |
| `API_KEY` | empty | Requires `X-API-Key` on API calls and `?api_key=` on EventSource streams. |
| `MAX_CONCURRENT_INVESTIGATIONS` | `5` | Limits investigations running at once. |
| `SKILL_TIMEOUT_SECONDS` | `120` | Maximum execution time for each skill. |

Gitea repository tools work without Bedrock. For Bedrock analysis, configure AWS credentials through environment variables, an AWS profile, or an attached IAM role, and ensure the selected model is available and permitted in `AWS_REGION`. Temporary credentials can include `AWS_SESSION_TOKEN`; boto3 picks it up automatically.

### Gitea MCP

The backend reads its enabled MCP servers from `backend/config/mcp_servers.yaml`.
Its `gitea` entry connects to the bundled HTTP MCP endpoint:
`http://localhost:8001/mcp`. Start `gitea_mcp/gitea_mcp_server.py`
before starting the backend. The backend forwards `GITEA_URL`,
`GITEA_OWNER`, `GITEA_REPO`, and `GITEA_TOKEN` from `backend/.env` as Gitea
headers; it does not read VS Code's credentials. Keep the backend alias `gitea`
so existing skills, repository investigations, and PR reviews remain unchanged.
Restart the backend after changing MCP configuration. `/api/config` reports
connection errors; `/api/skills` lists skills backed by discovered tools.

VS Code's separate client configuration is optional and is not published. The
in-process backend transport is still supported when explicitly configured with
`name: gitea`, `transport: inprocess`, and an `env` mapping containing the four
Gitea variables above. Gitea category routing and each tool's use are documented
in [.github/skills/gitea/SKILL.md](.github/skills/gitea/SKILL.md).

#### Evidence-first query workflow

In Auto mode, repository overview links deterministically select the Gitea overview workflow;
focused PR, issue, commit, branch, workflow, and release requests select their matching skills.

Paste a Gitea repository URL, or ask for a repository overview/deep dive, to run the read-only
ten-stage repository playbook, with each stage streamed separately in Agent Trace:

1. Repository name, ownership, metadata, languages, topics, and contributors.
2. Branch inventory.
3. Recent commits and default-branch latest SHA.
4. PR inventory and last merged PR (pages are inspected up to 500 PRs; incomplete history is labeled).
5. Issues, labels, and milestones.
6. Workflows, runs, tags, and releases.
7. Exact-SHA commit details, unified diff, and CI statuses.
8. Exact-SHA source tree and related-test discovery.
9. Changed implementations, related tests, and build manifests; source-grounded AI
   bug analysis when available, with a separate trace step for every diff batch.
10. Recovery review links, approval/validation guidance, and explicit evidence limitations.

Context reads prioritize changed files, then matching tests and project manifests
(up to 12 files, 16,000 characters per file, and 64,000 source characters per review).
Limits and unreadable context remain explicit evidence gaps. Native repository runs
include at least 19 trace steps (20 with one AI-reviewed diff batch); focused PR
reviews add evidence collection, source discovery, contextual reads, per-batch behavior
analysis, and final head revalidation. Counts reflect actual work, not fabricated traces.

Focused requests (for example, a particular PR, issue, or latest-commit question) keep their focused
skills. Repository investigations use read-only Gitea operations; mutating operations are not run.

The existing report layout now includes **MCP and Diagnostic Tool Results**, with each call's
source/mode, arguments, complete output, and success/failure. These results persist across reloads
and appear in JSON/Markdown exports. Missing tools, permissions, CI, AI review, or logs are
evidence gaps, never a clean-health verdict.
The report ends with a **Conclusion Summary** card containing the verdict, key
finding, coverage, code findings, limitations, and next action. Its additive
`conclusion_summary` field is persisted and exported; older reports display their
executive summary as a compatibility fallback.

Recovery links do **not** execute a revert. A returned commit link opens review. Failing CI is not proof of a code defect.
AI defect findings include source coordinates but are advisory: tests and production recovery are
not executed or verified by repository analysis. See [Repository Validation](docs/REPOSITORY_VALIDATION.md).

#### PR bug reviews and merge warnings

Ask the Gitea app to review a PR using its actual number or full Gitea URL. The
`Gitea Pull Requests` skill resolves the PR, reads its unified diff, existing
reviews, and CI status for its head SHA. It also reads changed source files,
discovers related tests and build manifests at that exact SHA, and checks changed
behavior, boundary/error paths, consumer contracts, and meaningful test assertions.
Missing context is a review limitation, not a code defect; unused mocks and
unfamiliar test names alone do not establish a bug.
Its review instructions are loaded from
[the PR review skill](backend/app/skills/playbooks/gitea-pr-review/SKILL.md);
this playbook is included in the backend package, not merely a VS Code customization.
Successful PR creation through this skill also triggers a review.

Detected defects, failed CI, and unresolved request-changes reviews produce a
**DO NOT MERGE** warning in the investigation report. Unavailable tools, 404s,
missing/pending CI, unavailable AI review, binary changes,
and an unverified/moved head produce **DO NOT MERGE -
review incomplete**. Report synthesis cannot remove these warnings.
The reviewer cites exact added lines; it does not execute tests and cannot
guarantee detection of every bug. Clean results remain advisory, not approval.
Each verified defect includes the affected file/line, faulty added code, failure
scenario, expected and actual behavior, impact, a concrete fix, and a suggested
regression test. These details are retained in the report and follow-up chat.
The reviewer receives a verified source-line map; indentation-only differences
and uniquely identifiable lines in the same file can be resolved without
inventing source. Unsupported citations get one correction attempt, then remain
explicitly unverified claims with the claimed file and issue visible. Missing CI
and unsupported claims are review limitations, not confirmed file corruption.
PR-related commit/status skills resolve the PR head before requesting CI; a PR
number is never used as the commit ref. Malformed reviewer JSON or missing schema
fields receive one format-correction retry. Persistent format failures remain
explicitly incomplete; connection errors are not retried as format failures.
Bedrock output-token limits trigger automatic suffix continuation, assembling
the full response before JSON/schema and source validation. Up to eight
continuations are allowed per answer to prevent runaway requests. Persistent
token limits, provider/context errors, and filtered output remain explicitly
incomplete; partial output is never accepted as a completed review. Content
filters are not bypassed.

Large diffs are reviewed in source-preserving batches (target 12,000 characters),
not rejected at 24,000 characters or sliced off. Large hunks retain file/line
coordinates when split. All batches are attempted, even if one fails; missing
cross-file context or failed batches remain explicit review limitations. The PR
skill has no whole-skill deadline, allowing all batches to finish; individual
tool/model requests still have timeouts, and cancellation remains available.
PR reports are assembled directly from the validated findings rather than sent
through a second, context-limited synthesis. All defect details and remediation
actions are retained. For follow-up answers exceeding the model context budget,
the full recorded PR explanation is returned directly instead of truncating it.

PR numbers share a sequence with issues: the first PR is not necessarily #1.
An explicit repository, PR, issue, file, or branch URL on the configured Gitea
server overrides `GITEA_OWNER`/`GITEA_REPO` for every Gitea call in that
investigation, including issue lookups and model-selected tools. The resolved
owner/name is recorded in the tool trace and overrides conflicting model args.
Defaults apply only when no repository link is supplied. Multiple linked
repositories require separate investigations. PR/issue links to another server
are rejected explicitly, not redirected to the default repository; configure
that server separately. This does not change global settings or forward tokens
to a server supplied in chat.
Use `list_pull_requests` to discover the actual number. A 404 can mean a wrong
repository/number or insufficient token access, not successful validation.
Creating a PR directly on Gitea does not trigger this app automatically.
These report warnings neither post remote reviews nor enforce branch protection; automatic checks
require a separately configured Gitea Actions workflow.

## Add Skills

Built-in Gitea skills are Python classes under `backend/app/skills/builtin/` and are registered in `backend/app/skills/registry.py`.

## Add Orchestrators

Implement `Orchestrator.run(ctx)` and decorate the class with `@register_orchestrator("your_name")`. Import the module in `backend/app/orchestration/base.py` inside `_load_builtin`, then set `ORCHESTRATOR=your_name`. Use `RunContext` to emit steps, plans, timelines, and reports; framework integrations such as LangGraph or CrewAI should remain behind this interface.

## Local Test Suites

Test files/folders are not published. If you have local suites separately,
install `python -m pip install -e './backend[test]'` and run
`python automation/validate.py --include-tests`. For a fresh clone use the
validation and live smoke-check steps above.