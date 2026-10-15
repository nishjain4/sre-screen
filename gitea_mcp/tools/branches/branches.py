"""Tools for listing and managing repository branches."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, request, require_confirmation


def register_branch_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_branches(page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository branches with pagination."""
        return request(client, "GET", "/branches", owner=owner, reponame=reponame, url=url, params={"page": page, "limit": limit})

    @mcp.tool()
    def get_branch(branch: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return branch details and its head commit."""
        return request(client, "GET", f"/branches/{path_segment(branch)}", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def create_branch(branch_name: str, old_branch_name: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a branch from a source branch or commit."""
        return request(client, "POST", "/branches", owner=owner, reponame=reponame, url=url, body={"new_branch_name": branch_name, "old_branch_name": old_branch_name})

    @mcp.tool()
    def delete_branch(branch: str, confirm: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Delete a non-protected branch after explicit confirmation."""
        require_confirmation(confirm, "delete this branch")
        return request(client, "DELETE", f"/branches/{path_segment(branch)}", owner=owner, reponame=reponame, url=url)