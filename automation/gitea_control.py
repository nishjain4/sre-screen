"""Trusted Gitea notification and confirmation-gated revert worker."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.integrations.mcp_servers.gitea_server import GiteaAPI, handle_message


SHA = re.compile(r"[0-9a-f]{40}\Z")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Control:
    def __init__(self) -> None:
        self.base = os.environ["GITEA_SERVER_URL"].rstrip("/")
        parsed = urlsplit(self.base)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("GITEA_SERVER_URL must be an HTTPS origin/path without credentials")
        self.repository = os.environ["GITEA_REPOSITORY"]
        owner, repo = self.repository.split("/")
        self.api = GiteaAPI(self.base, os.environ["GITEA_CONTROL_TOKEN"], owner, repo)
        self.repo_url = f"{self.base}/{quote(owner, safe='')}/{quote(repo, safe='')}"
        control_repo = os.environ["GITEA_CONTROL_REPOSITORY"]
        control_owner, control_name = control_repo.split("/")
        control_url = f"{self.base}/{quote(control_owner, safe='')}/{quote(control_name, safe='')}"
        self.run_url = f"{control_url}/actions/runs/{quote(os.environ['GITEA_RUN_ID'], safe='')}"
        self.http = httpx.AsyncClient(headers={"Authorization": f"token {self.api.token}",
                                               "Accept": "application/json"}, timeout=30,
                                      follow_redirects=False)

    async def mcp(self, name: str, **arguments):
        response = await handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                         "params": {"name": name, "arguments": arguments}}, self.api, self.http)
        result = response["result"]
        if result.get("isError"):
            raise RuntimeError(f"Gitea MCP operation {name} failed")
        return result["structuredContent"]

    async def rest(self, method: str, path: str, body: dict | None = None):
        response = await self.http.request(method, f"{self.base}/api/v1{path}", json=body)
        response.raise_for_status()
        return response.json() if response.content else None

    async def poll(self) -> None:
        state = Path(os.environ["GUARD_STATE_PATH"])
        state.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(state, timeout=30) as ledger:
            ledger.execute("CREATE TABLE IF NOT EXISTS reported_runs "
                           "(repository TEXT, run_id INTEGER, version TEXT, reported_at TEXT, "
                           "PRIMARY KEY(repository, run_id, version))")
        failures = []
        for page in range(1, 21):
            data = await self.mcp("list_workflow_runs", workflow_id="validate.yml", limit=50, page=page)
            runs = data.get("workflow_runs", [])
            for run in runs:
                workflow = str(run.get("workflow_id", run.get("path", "")))
                if not (workflow.endswith("validate.yml") or run.get("name") == "Repository Validation"):
                    continue
                result = run.get("conclusion") or run.get("status")
                if result not in {"success", "failure", "cancelled", "skipped", "timed_out", "action_required"}:
                    continue
                sha = run["head_sha"]
                if not SHA.fullmatch(sha):
                    continue
                version = hashlib.sha256(str(run.get("updated_at", "")).encode()).hexdigest()[:16]
                with sqlite3.connect(state, timeout=30) as ledger:
                    already_reported = ledger.execute(
                        "SELECT 1 FROM reported_runs WHERE repository=? AND run_id=? AND version=?",
                        (self.repository, int(run["id"]), version)).fetchone()
                if already_reported:
                    continue
                self.run_url = f"{self.repo_url}/actions/runs/{int(run['id'])}#sre-{version}"
                statuses = await self.mcp("list_commit_statuses", ref=sha)
                if any(status.get("context") == "sre/validation" and status.get("target_url") == self.run_url
                       for status in statuses):
                    continue
                try:
                    report = await self.download_report(int(run["id"]))
                    with tempfile.TemporaryDirectory(prefix="sre-report-") as temporary:
                        path = Path(temporary) / "report.json"
                        if report is not None:
                            path.write_text(json.dumps(report), encoding="utf-8")
                        event = {"after": sha, "ref": f"refs/heads/{run['head_branch']}"}
                        prs = await self.mcp("list_pull_requests", state="all", limit=50, page=1)
                        pr = next((item for item in prs if item.get("head", {}).get("sha") == sha), None)
                        if pr:
                            event["pull_request"] = pr
                        os.environ.update(GITEA_EVENT_JSON=json.dumps(event), VALIDATION_REPORT=str(path),
                                          VALIDATION_JOB_RESULT="success" if result == "success" else "failure")
                        with sqlite3.connect(state, timeout=30) as ledger:
                            ledger.execute("BEGIN IMMEDIATE")
                            if ledger.execute("SELECT 1 FROM reported_runs WHERE repository=? AND run_id=? AND version=?",
                                              (self.repository, int(run["id"]), version)).fetchone():
                                continue
                            await self.publish()
                            ledger.execute("INSERT INTO reported_runs VALUES (?, ?, ?, ?)",
                                           (self.repository, int(run["id"]), version, now()))
                except Exception as exc:
                    failures.append(f"Run {run['id']}: {type(exc).__name__}")
            if len(runs) < 50:
                if failures:
                    raise RuntimeError("Some reports failed and will be retried: " + ", ".join(failures))
                return
        raise RuntimeError("Reporter scan capacity reached; increase capacity or deploy a durable event consumer")

    async def download_report(self, run_id: int) -> dict | None:
        prefix = self.api._repo_path({})
        data = await self.rest("GET", prefix + f"/actions/runs/{run_id}/artifacts")
        artifact = next((item for item in data.get("artifacts", [])
                         if item.get("name") == "validation-results" and not item.get("expired")), None)
        if artifact is None:
            return None
        content = bytearray()
        async with self.http.stream("GET", f"{self.base}/api/v1{prefix}/actions/artifacts/{int(artifact['id'])}/zip") as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > 32 * 1024 * 1024:
                    raise ValueError("Validation artifact exceeds the 32 MiB controller limit")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [member for member in archive.infolist()
                       if member.filename in {"report.json", "validation-results/report.json"}]
            if len(members) != 1 or members[0].file_size > 1024 * 1024:
                raise ValueError("Expected one bounded report.json in the artifact")
            report = json.loads(archive.read(members[0]))
        if not isinstance(report, dict) or report.get("status") not in {"passed", "failed"}:
            raise ValueError("Invalid validation report")
        return report

    async def publish(self) -> None:
        event = json.loads(os.environ["GITEA_EVENT_JSON"])
        pull = event.get("pull_request")
        sha = pull["head"]["sha"] if pull else event["after"]
        branch = pull["head"]["ref"] if pull else event["ref"].removeprefix("refs/heads/")
        if not SHA.fullmatch(sha):
            raise ValueError("Invalid event commit ID")
        path = Path(os.environ.get("VALIDATION_REPORT", "validation-results/report.json"))
        if path.exists():
            report = json.loads(path.read_text(encoding="utf-8"))
        else:
            report = {"status": "failed", "timestamp": now(), "checks": [
                {"name": "runner-or-setup", "status": "failed"}]}
        job_result = os.environ.get("VALIDATION_JOB_RESULT", "failure")
        failed = job_result != "success" or report.get("status") != "passed"
        failures = [check["name"] for check in report.get("checks", []) if check.get("status") != "passed"]
        if failed and not failures:
            failures = ["runner, setup, or artifact upload failed"]
        status = {
            "state": "failure" if failed else "success", "context": "sre/validation",
            "target_url": self.run_url, "description": (", ".join(failures) or "All checks passed")[:140]}
        commit = await self.mcp("get_commit", ref=sha)
        message = commit.get("commit", {}).get("message", "")
        if not failed:
            await self.rest("POST", self.api._repo_path({}) + f"/statuses/{sha}", status)
            return
        author = commit.get("commit", {}).get("author", {}).get("name", "unknown")
        before = event.get("before") or next(iter(commit.get("parents", [])), {}).get("sha", sha)
        if not SHA.fullmatch(before) or before == "0" * 40:
            before = sha
        marker = f"<!-- sre-validation:{sha}:{hashlib.sha256(branch.encode()).hexdigest()[:16]} -->"
        pr_url = f"{self.repo_url}/pulls/{int(pull['number'])}" if pull else "Not applicable (push event)"
        body = "\n".join([
            marker, "## Potentially Faulty Change", "",
            f"Repository: {self.repository}", f"Branch: `{branch}`", f"Commit: `{sha}`",
            f"Author: {author}", f"Detection timestamp: {now()}",
            "Failure reason: " + ", ".join(failures),
            f"[Validation logs and report artifacts]({self.run_url})",
            f"[Commit]({self.repo_url}/commit/{sha})",
            f"[Compare]({self.repo_url}/compare/{before}...{sha})", f"Pull request: {pr_url}", "",
            "Suggested action: review the logs and report, then fix forward in a reviewed change.",
            "", "Validation summary:", "```json", json.dumps(report, indent=2)[:16000], "```",
        ])
        existing = None
        for page in range(1, 101):
            issues = await self.mcp("list_issues", state="all", limit=50, page=page)
            existing = next((issue for issue in issues if marker in (issue.get("body") or "")), None)
            if existing or len(issues) < 50:
                break
        else:
            raise RuntimeError("Issue search exceeded its bound; refusing to create a possible duplicate alert")
        if existing:
            issue = existing
        else:
            issue = await self.mcp("create_issue", title=f"[Validation failed] {branch[:80]} @ {sha[:12]}",
                                   body=body, assignees=[value.strip() for value in
                                   os.environ.get("GITEA_ALERT_ASSIGNEES", "").split(",") if value.strip()])
        print(f"Failure alert: {self.repo_url}/issues/{issue['number']}")
        await self.rest("POST", self.api._repo_path({}) + f"/statuses/{sha}", status)

async def main() -> None:
    control = Control()
    try:
        if sys.argv[1:] == ["poll"]:
            await control.poll()
        elif sys.argv[1:] == ["publish"]:
            await control.publish()
        else:
            raise ValueError("Expected poll or publish")
    finally:
        await control.http.aclose()


if __name__ == "__main__":
    asyncio.run(main())