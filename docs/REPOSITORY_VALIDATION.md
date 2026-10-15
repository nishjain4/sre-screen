# Repository Validation Reporting

The source workflow in `.gitea/workflows/validate.yml` runs credential-free static, build, and startup health checks. It publishes `report.json`, `report.md`, and per-check logs as a workflow artifact. Test files and folders are intentionally not published.

The optional controller workflow in `automation/control-workflows/report.yml` polls completed source runs and publishes a Gitea issue plus commit status for failures. It does not deploy, revert commits, or modify source branches.

## Setup

1. Enable Gitea Actions and configure an isolated runner for source validation. Do not expose production or repository-write credentials to source jobs.
2. Place `report.yml` in the trusted controller repository under `.gitea/workflows/`, protect its default branch, and run it on a trusted controller runner.
3. Set `VALIDATION_REPOSITORY` to the source repository and `VALIDATION_WORKER_SHA` to a reviewed immutable commit containing the reporter code.
4. Set the `VALIDATION_REPORT_TOKEN` secret with only the permissions needed to read workflow runs/artifacts and publish commit statuses/issues to the source repository.
5. Mount persistent controller storage at `/var/lib/sre-guard/` for the reporter's SQLite idempotency ledger.

Pin third-party actions to reviewed immutable revisions and restrict controller access to trusted maintainers. Validate the complete flow in a staging repository before relying on notifications.

## Local Checks

From the repository root, install `python -m pip install -e ./backend -r automation/requirements.txt -r gitea_mcp/requirements.txt`, run `npm ci` in `frontend`, then run `python automation/validate.py`. Requires Python 3.14 and Node.js 22 or newer; Docker, AWS credentials, and a live Gitea server are not needed.

This verifies static checks, backend packaging, frontend type checking/build, and offline application startup/health/shutdown. It does not verify live Gitea access or Bedrock. See the root README for live smoke-check steps.

If local test folders are available separately, install `python -m pip install -e './backend[test]'` and use `python automation/validate.py --include-tests`. That option fails explicitly when no local test folders exist; it is not required for a fresh clone.
