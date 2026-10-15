"""Tools for repository issues and comments."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import provided, request


def register_issue_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_issues(state: str | None = None, labels: str | None = None, milestone: int | None = None, since: str | None = None, before: str | None = None, created_by: str | None = None, assigned_by: str | None = None, mentioned: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List issues and pull-request conversations with filters and pagination."""
        params = provided(state=state, labels=labels, milestone=milestone, since=since, before=before, created_by=created_by, assigned_by=assigned_by, mentioned=mentioned, page=page, limit=limit)
        return request(client, "GET", "/issues", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def create_issue(title: str, body: str | None = None, assignees: list[str] | None = None, labels: list[int] | None = None, milestone: int | None = None, due_date: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create an issue with optional assignees, labels, and milestone."""
        payload = {"title": title, **provided(body=body, assignees=assignees, labels=labels, milestone=milestone, due_date=due_date)}
        return request(client, "POST", "/issues", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def get_issue(index: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return a single issue or pull-request conversation."""
        return request(client, "GET", f"/issues/{index}", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def update_issue(index: int, title: str | None = None, body: str | None = None, state: str | None = None, labels: list[int] | None = None, assignees: list[str] | None = None, milestone: int | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Update issue title, body, state, labels, assignees, or milestone."""
        payload = provided(title=title, body=body, state=state, labels=labels, assignees=assignees, milestone=milestone)
        if not payload:
            raise ValueError("Provide at least one issue field to update")
        return request(client, "PATCH", f"/issues/{index}", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def list_issue_comments(index: int, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List comments on an issue or pull request."""
        return request(client, "GET", f"/issues/{index}/comments", owner=owner, reponame=reponame, url=url, params={"page": page, "limit": limit})

    @mcp.tool()
    def add_issue_comment(index: int, body: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Add a comment to an issue or pull request."""
        return request(client, "POST", f"/issues/{index}/comments", owner=owner, reponame=reponame, url=url, body={"body": body})