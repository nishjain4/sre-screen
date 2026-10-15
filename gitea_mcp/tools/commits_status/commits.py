"""Tools for repository commits and commit statuses."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, provided, request


def register_commit_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_commits(sha: str | None = None, path: str | None = None, author: str | None = None, since: str | None = None, until: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List commits filtered by ref, path, author, or date range."""
        params = provided(sha=sha, path=path, author=author, since=since, until=until, page=page, limit=limit)
        return request(client, "GET", "/commits", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def get_commit(sha: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return a Git commit by SHA."""
        return request(client, "GET", f"/git/commits/{path_segment(sha)}", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_commit_status(ref: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return combined commit status for a ref."""
        return request(client, "GET", f"/commits/{path_segment(ref)}/status", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def list_commit_statuses(ref: str, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List individual commit statuses for a ref."""
        return request(client, "GET", f"/commits/{path_segment(ref)}/statuses", owner=owner, reponame=reponame, url=url)