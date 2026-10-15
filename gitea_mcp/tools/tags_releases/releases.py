"""Tools for repository tags and releases."""

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, provided, request, require_confirmation


def register_release_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_tags(page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository tags with pagination."""
        return request(client, "GET", "/tags", owner=owner, reponame=reponame, url=url, params={"page": page, "limit": limit})

    @mcp.tool()
    def list_releases(page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository releases with pagination."""
        return request(client, "GET", "/releases", owner=owner, reponame=reponame, url=url, params={"page": page, "limit": limit})

    @mcp.tool()
    def create_release(tag_name: str, name: str, body: str | None = None, target_commitish: str | None = None, draft: bool = False, prerelease: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a release or draft release for a tag."""
        payload = {"tag_name": tag_name, "name": name, "draft": draft, "prerelease": prerelease, **provided(body=body, target_commitish=target_commitish)}
        return request(client, "POST", "/releases", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def get_release(release_id: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Return a release by numeric ID."""
        return request(client, "GET", f"/releases/{release_id}", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def delete_release(release_id: int, confirm: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Delete a release after explicit confirmation."""
        require_confirmation(confirm, "delete this release")
        return request(client, "DELETE", f"/releases/{release_id}", owner=owner, reponame=reponame, url=url)