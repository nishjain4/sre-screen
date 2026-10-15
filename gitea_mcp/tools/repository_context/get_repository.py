"""Repository metadata and activity tools."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import request


def register_repository_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def get_repository(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return repository metadata, permissions, and default branch."""
        return request(client, "GET", "", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_repository_languages(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return detected language byte counts."""
        return request(client, "GET", "/languages", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_repository_topics(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """Return repository topics."""
        return request(client, "GET", "/topics", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_contributors(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository contributors."""
        return request(client, "GET", "/contributors", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_contributor_stats(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """Return contributor statistics."""
        return request(client, "GET", "/stats/contributors", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def get_commit_stats(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """Return commit activity statistics."""
        return request(client, "GET", "/stats/commit_activity", owner=owner, reponame=reponame, url=url)