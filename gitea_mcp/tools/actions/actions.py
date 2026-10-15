"""Tools for repository Actions workflows and runs."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, provided, request


def register_action_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_workflows(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """List repository Actions workflows."""
        return request(client, "GET", "/actions/workflows", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def list_workflow_runs(workflow_id: str | None = None, actor: str | None = None, branch: str | None = None, event: str | None = None, status: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """List workflow runs by workflow, actor, branch, event, or status."""
        params = provided(workflow_id=workflow_id, actor=actor, branch=branch, event=event, status=status, page=page, limit=limit)
        return request(client, "GET", "/actions/runs", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def trigger_workflow(workflow_id: str, ref: str, inputs: dict[str, str] | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Dispatch a workflow on a ref with optional approved inputs."""
        body = {"ref": ref, **provided(inputs=inputs)}
        endpoint = f"/actions/workflows/{path_segment(workflow_id)}/dispatches"
        return request(client, "POST", endpoint, owner=owner, reponame=reponame, url=url, body=body)