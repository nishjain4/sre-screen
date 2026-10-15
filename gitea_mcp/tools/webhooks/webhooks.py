"""Tools for repository webhooks."""

from typing import Any

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import request, require_confirmation


def register_webhook_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_webhooks(owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List repository webhooks."""
        return request(client, "GET", "/hooks", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def create_webhook(config: dict[str, str], events: list[str], active: bool = True, webhook_type: str = "gitea", owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a webhook; config should include the target URL and any required secret."""
        if not config.get("url"):
            raise ValueError("config must include a webhook target under the 'url' key")
        body: dict[str, Any] = {"type": webhook_type, "config": config, "events": events, "active": active}
        return request(client, "POST", "/hooks", owner=owner, reponame=reponame, url=url, body=body)

    @mcp.tool()
    def delete_webhook(hook_id: int, confirm: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Delete a repository webhook after explicit confirmation."""
        require_confirmation(confirm, "delete this webhook")
        return request(client, "DELETE", f"/hooks/{hook_id}", owner=owner, reponame=reponame, url=url)