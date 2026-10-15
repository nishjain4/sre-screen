"""Tools for repository labels and milestones."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import provided, request


def register_label_milestone_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_labels(page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository labels with pagination."""
        return request(client, "GET", "/labels", owner=owner, reponame=reponame, url=url, params={"page": page, "limit": limit})

    @mcp.tool()
    def create_label(name: str, color: str, description: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a repository label; color is a hexadecimal value such as FFFFFF."""
        payload = {"name": name, "color": color.lstrip("#"), **provided(description=description)}
        return request(client, "POST", "/labels", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def list_milestones(state: str | None = None, sort: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository milestones by state and pagination."""
        params = provided(state=state, sort=sort, page=page, limit=limit)
        return request(client, "GET", "/milestones", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def create_milestone(title: str, description: str | None = None, state: str | None = None, due_on: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a milestone with optional description, state, and due date."""
        payload = {"title": title, **provided(description=description, state=state, due_on=due_on)}
        return request(client, "POST", "/milestones", owner=owner, reponame=reponame, url=url, body=payload)